#import <Cocoa/Cocoa.h>
int main(int argc, const char *argv[]) {
    @autoreleasepool {
        NSDictionary *info = NSBundle.mainBundle.infoDictionary;
        NSString *package = info[@"AndroidPackage"];
        NSString *appPath = info[@"SubsystemAppPath"];
        if (!package || !appPath) return 1;
        NSURLComponents *components = [[NSURLComponents alloc] init];
        components.scheme = @"android-subsystem"; components.host = @"launch";
        components.queryItems = @[[NSURLQueryItem queryItemWithName:@"package" value:package]];
        NSWorkspaceOpenConfiguration *config = [NSWorkspaceOpenConfiguration configuration];
        __block BOOL finished = NO;
        __block BOOL failed = NO;
        [NSWorkspace.sharedWorkspace openURLs:@[components.URL]
                      withApplicationAtURL:[NSURL fileURLWithPath:appPath]
                             configuration:config
                         completionHandler:^(NSRunningApplication *app, NSError *error) {
            failed = error != nil; finished = YES;
        }];
        NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:20];
        while (!finished && [deadline timeIntervalSinceNow] > 0) {
            [NSRunLoop.currentRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
        }
        return finished && !failed ? 0 : 1;
    }
}
