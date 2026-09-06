import ActivityKit
import Foundation

/// Starts / updates / ends a Live Activity locally (no push), and registers the
/// push-to-start token + the per-activity push token as iOS issues them.
///
/// The S3 "done" bar is: `startLocally()` puts a Live Activity on the lock screen
/// of a physical device. That proves ActivityKit works before APNs is involved.
@MainActor
final class LiveActivityController: ObservableObject {
    private let model = ProbeModel.shared

    @Published private(set) var current: Activity<CommuteActivityAttributes>?

    // MARK: - Push-to-start token (iOS 17.2+)

    /// Call once at launch. iOS delivers the push-to-start token asynchronously,
    /// and re-delivers it whenever it rotates.
    func observePushToStartToken() {
        guard #available(iOS 17.2, *) else {
            model.log("push-to-start UNAVAILABLE: iOS < 17.2")
            return
        }
        if let existing = Activity<CommuteActivityAttributes>.pushToStartToken {
            model.set(.pushToStart, ProbeModel.hex(existing))
        }
        Task {
            for await tokenData in Activity<CommuteActivityAttributes>.pushToStartTokenUpdates {
                model.set(.pushToStart, ProbeModel.hex(tokenData))
            }
        }
    }

    // MARK: - Local lifecycle

    func startLocally() {
        let auth = ActivityAuthorizationInfo()
        guard auth.areActivitiesEnabled else {
            model.log("cannot start: Live Activities disabled (Settings > S3 Probe > Live Activities)")
            return
        }
        let attributes = CommuteActivityAttributes(routeName: "CR-Worcester", stopName: "Boston Landing")
        let initial = CommuteActivityAttributes.ContentState(
            displayStatus: "on_time",
            headline: "Local start — no push involved",
            minutesToDeparture: 12)
        do {
            let activity = try Activity.request(
                attributes: attributes,
                content: .init(state: initial, staleDate: nil),
                pushType: .token)
            current = activity
            model.setActivityState("\(activity.activityState)")
            model.log("started activity id=\(activity.id)")
            observe(activity)
        } catch {
            model.log("Activity.request FAILED: \(error.localizedDescription)")
        }
    }

    func bumpUpdate() {
        guard let activity = current else { model.log("no active activity to update"); return }
        Task {
            let next = CommuteActivityAttributes.ContentState(
                displayStatus: "delayed",
                headline: "Local update at \(shortTime())",
                minutesToDeparture: Int.random(in: 1...20))
            await activity.update(.init(state: next, staleDate: nil))
            model.log("local update applied")
        }
    }

    func endActivity() {
        guard let activity = current else { model.log("no active activity to end"); return }
        Task {
            await activity.end(nil, dismissalPolicy: .immediate)
            model.log("activity ended (immediate)")
            current = nil
        }
    }

    // MARK: - Per-activity token + state observation

    private func observe(_ activity: Activity<CommuteActivityAttributes>) {
        if let token = activity.pushToken {
            model.set(.activity, ProbeModel.hex(token))
        }
        Task {
            for await tokenData in activity.pushTokenUpdates {
                model.set(.activity, ProbeModel.hex(tokenData))
            }
        }
        Task {
            for await state in activity.activityStateUpdates {
                model.setActivityState("\(state)")
            }
        }
    }

    private func shortTime() -> String {
        let f = DateFormatter()
        f.timeStyle = .medium
        return f.string(from: .now)
    }
}
