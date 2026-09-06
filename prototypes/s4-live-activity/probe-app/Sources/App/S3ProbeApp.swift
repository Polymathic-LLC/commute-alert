import SwiftUI

@main
struct S3ProbeApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(ProbeModel.shared)
        }
    }
}
