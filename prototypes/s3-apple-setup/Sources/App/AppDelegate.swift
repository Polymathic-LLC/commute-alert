import UIKit

/// Registers for a standard APNs device token so S2/S4 can also exercise the
/// alert and background (widget) push types against this build.
final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        UIApplication.shared.registerForRemoteNotifications()
        return true
    }

    func application(_ application: UIApplication,
                     didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        Task { @MainActor in
            ProbeModel.shared.set(.apnsDevice, ProbeModel.hex(deviceToken))
        }
    }

    func application(_ application: UIApplication,
                     didFailToRegisterForRemoteNotificationsWithError error: Error) {
        Task { @MainActor in
            ProbeModel.shared.log("APNs device-token registration FAILED: \(error.localizedDescription)")
        }
    }

    /// Background push arrives here (apns-push-type: background). S4 uses this to
    /// eyeball the widget background-push budget.
    func application(_ application: UIApplication,
                     didReceiveRemoteNotification userInfo: [AnyHashable: Any]) async -> UIBackgroundFetchResult {
        await MainActor.run {
            ProbeModel.shared.log("background push received: \(userInfo)")
        }
        return .newData
    }
}
