// SPDX-License-Identifier: GPL-3.0-or-later
// Launch the bundled ARM64 runtime with separate settings and memory cards.
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#import <AppKit/AppKit.h>
#include <sys/file.h>

static int fail(NSString* message)
{
    fprintf(stderr, "%s\n", message.UTF8String);
    [NSApplication sharedApplication];
    NSAlert* alert = [NSAlert new];
    alert.messageText = @"Melee could not start";
    alert.informativeText = message;
    [alert runModal];
    return 1;
}

int main(int argc, const char* argv[])
{
    @autoreleasepool {
        NSFileManager* manager = NSFileManager.defaultManager;
        NSBundle* bundle = NSBundle.mainBundle;
        NSString* resources = bundle.resourcePath;
        NSString* runtime =
            [bundle.executablePath.stringByDeletingLastPathComponent
                stringByAppendingPathComponent:@"MeleeRuntime"];
        NSString* game = [resources stringByAppendingPathComponent:@"Game"];
        NSString* module = [resources
            stringByAppendingPathComponent:@"Module/gGALE01_recomp.dylib"];
        NSString* support =
            [manager URLsForDirectory:NSApplicationSupportDirectory
                            inDomains:NSUserDomainMask]
                .firstObject.path;
        NSString* user =
            [support stringByAppendingPathComponent:@"t3.melee.native"];
        const char* override = getenv("MELEE_USER_DIR");
        if (override != NULL) {
            user = @(override);
            if (!user.isAbsolutePath) {
                return fail(@"MELEE_USER_DIR must be an absolute path.");
            }
        }
        NSString* config = [user stringByAppendingPathComponent:@"Config"];
        NSString* logs = [NSHomeDirectory()
            stringByAppendingPathComponent:@"Library/Logs/t3.melee.native"];
        NSError* error = nil;
        for (NSString* directory in @[ config, logs ]) {
            if (![manager createDirectoryAtPath:directory
                    withIntermediateDirectories:YES
                                     attributes:@{
                                         NSFilePosixPermissions : @0700
                                     }
                                          error:&error])
            {
                return fail(error.localizedDescription);
            }
        }
        int lock = open([user stringByAppendingPathComponent:@"session.lock"]
                            .fileSystemRepresentation,
                        O_CREAT | O_RDWR, 0600);
        if (lock < 0 || flock(lock, LOCK_EX | LOCK_NB) < 0) {
            return fail(@"Another Melee session uses this save folder. Close "
                        @"it before starting another game.");
        }
        // Keep the lock across exec so two sessions cannot write the same
        // card.
        NSString* logfile = [logs stringByAppendingPathComponent:@"app.log"];
        int log = open(logfile.fileSystemRepresentation,
                       O_WRONLY | O_CREAT | O_APPEND, 0600);
        if (log < 0) {
            return fail(
                [@"Could not open the log: " stringByAppendingString:logfile]);
        }
        dup2(log, STDOUT_FILENO);
        dup2(log, STDERR_FILENO);
        close(log);
        fprintf(stderr, "\nMelee launch: %s\nSave folder: %s\n",
                NSDate.date.description.UTF8String,
                user.fileSystemRepresentation);
        for (NSString* path in @[
                 runtime, module,
                 [game stringByAppendingPathComponent:@"sys/main.dol"]
             ])
        {
            if (![manager fileExistsAtPath:path]) {
                return fail([@"The app is missing a required file: "
                    stringByAppendingString:path]);
            }
        }
        NSString* padConfig =
            [config stringByAppendingPathComponent:@"GCPadNew.ini"];
        if (![manager fileExistsAtPath:padConfig] &&
            ![manager copyItemAtPath:[resources stringByAppendingPathComponent:
                                                    @"Defaults/GCPadNew.ini"]
                              toPath:padConfig
                               error:&error])
        {
            return fail(error.localizedDescription);
        }
        NSString* runtimeConfig =
            [user stringByAppendingPathComponent:@"config.ini"];
        if (![manager fileExistsAtPath:runtimeConfig]) {
            NSData* defaults =
                [@"resolution=640x528\nshow_fps_in_title=true\nfullscreen="
                 @"false\n" dataUsingEncoding:NSUTF8StringEncoding];
            if (![defaults writeToFile:runtimeConfig
                               options:NSDataWritingWithoutOverwriting
                                 error:&error])
            {
                return fail(error.localizedDescription);
            }
        }
        setenv("MODERNGEKKO_STATICRECOMP", "1", 1);
        setenv("MELEE_STRICT_NATIVE", "1", 1);
        setenv("MELEE_APP_BUNDLE", "1", 1);
        setenv("MELEE_FRONTEND", "1", 0);
        unsetenv("MELEE_WORKSPACE");
        NSMutableArray<NSString*>* arguments = [@[
            runtime, @"--game", game, @"--module", module, @"--user-dir", user,
            @"--graphics", @"Metal", @"--audio", @"Cubeb", @"--no-mods"
        ] mutableCopy];
        for (int i = 1; i < argc; ++i) {
            // Finder adds this legacy argument on some launch paths.
            if (strncmp(argv[i], "-psn_", 5) != 0) {
                [arguments addObject:@(argv[i])];
            }
        }
        char** args = calloc(arguments.count + 1, sizeof(char*));
        if (args == NULL) {
            return fail(@"Could not allocate launch arguments.");
        }
        for (NSUInteger i = 0; i < arguments.count; ++i) {
            args[i] = (char*) arguments[i].UTF8String;
        }
        if (chdir(resources.fileSystemRepresentation) != 0) {
            return fail(@"Could not open the app resources folder.");
        }
        execv(runtime.fileSystemRepresentation, args);
        return fail([NSString
            stringWithFormat:@"Could not launch the game: %s. Details: %@",
                             strerror(errno), logfile]);
    }
}
