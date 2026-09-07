import ActivityKit
import Foundation

/// Starts / updates / ends Live Activities locally, and registers push tokens as
/// iOS issues them.
///
/// S4 CHANGES, and why each one exists
/// -----------------------------------
/// 1. `observeAllActivities()` watches `Activity.activityUpdates`, the sequence of
///    activities appearing by **any** route — including ones the backend started
///    by push. The original wired `pushTokenUpdates` only inside `startLocally()`,
///    so a push-started activity's token was never seen and that activity could
///    never be updated. That is finding F4, and it is a trap a production app
///    would fall into: capture wired into your own start path passes every local
///    test and fails in the field, where the server does the starting.
///
/// 2. `contentUpdates` is logged per activity — instrument I2. While the app is
///    alive this is exact ground truth for "ActivityKit applied this update",
///    used to calibrate the widget render log (I1) in E0.
///
/// 3. A snapshot of `Activity.activities` on demand — instrument I3.
///
/// 4. `startBatch` / `endAll` for the concurrency and ending experiments.
@MainActor
final class LiveActivityController: ObservableObject {
    private let model = ProbeModel.shared

    @Published private(set) var current: Activity<CommuteActivityAttributes>?
    @Published private(set) var liveCount: Int = 0

    /// Activities already wired for token + content observation, by id, so a
    /// re-delivery from `activityUpdates` does not start duplicate tasks.
    private var observed: Set<String> = []

    // MARK: - Push-to-start token (iOS 17.2+)

    func observePushToStartToken() {
        guard #available(iOS 17.2, *) else {
            model.log("push-to-start UNAVAILABLE: iOS < 17.2")
            return
        }
        if let existing = Activity<CommuteActivityAttributes>.pushToStartToken {
            model.set(.pushToStart, ProbeModel.hex(existing))
            S4Log.write(src: "app", event: "pts_token", fields: ["token": ProbeModel.hex(existing)])
        }
        Task {
            for await tokenData in Activity<CommuteActivityAttributes>.pushToStartTokenUpdates {
                let hex = ProbeModel.hex(tokenData)
                model.set(.pushToStart, hex)
                // Logged on every delivery, so a rotation across reboot or
                // reinstall is visible in the record rather than inferred.
                S4Log.write(src: "app", event: "pts_token", fields: ["token": hex])
            }
        }
    }

    // MARK: - F4 fix: observe every activity, however it was started

    /// Call once at launch. Picks up activities that already exist (app was
    /// relaunched, or the backend started one while the app was dead) and every
    /// activity that appears later.
    func observeAllActivities() {
        for activity in Activity<CommuteActivityAttributes>.activities {
            adopt(activity, origin: "existing_at_launch")
        }
        refreshCount()
        Task {
            for await activity in Activity<CommuteActivityAttributes>.activityUpdates {
                adopt(activity, origin: "activityUpdates")
                refreshCount()
            }
        }
    }

    private func adopt(_ activity: Activity<CommuteActivityAttributes>, origin: String) {
        guard !observed.contains(activity.id) else { return }
        observed.insert(activity.id)

        model.log("adopted activity \(activity.id) via \(origin) — \(activity.attributes.routeName)")
        S4Log.write(src: "app", event: "activity_adopted", fields: [
            "id": activity.id,
            "origin": origin,
            "routeName": activity.attributes.routeName,
            "state": "\(activity.activityState)",
            "headline": activity.content.state.headline,
        ])

        if let token = activity.pushToken {
            record(token: token, for: activity)
        }
        Task {
            for await tokenData in activity.pushTokenUpdates {
                record(token: tokenData, for: activity)
            }
        }
        // I2 — exact record of every content state ActivityKit applies while the
        // app is alive. `updatedAt` is logged as the *decoded* Date, which is
        // what settles which epoch the push decoder reads a numeric Date
        // against — by instrument, with no human squinting at a timestamp.
        Task {
            for await content in activity.contentUpdates {
                S4Log.write(src: "app", event: "content_update", fields: [
                    "id": activity.id,
                    "headline": content.state.headline,
                    "displayStatus": content.state.displayStatus,
                    "v": String(content.state.v),
                    "minutes": content.state.minutesToDeparture.map(String.init) ?? "",
                    "updatedAtDecoded": ISO8601DateFormatter().string(from: content.state.updatedAt),
                ])
            }
        }
        Task {
            for await state in activity.activityStateUpdates {
                model.setActivityState("\(state)")
                S4Log.write(src: "app", event: "activity_state", fields: [
                    "id": activity.id, "state": "\(state)",
                ])
                refreshCount()
            }
        }
    }

    private func record(token: Data, for activity: Activity<CommuteActivityAttributes>) {
        let hex = ProbeModel.hex(token)
        model.set(.activity, hex)
        S4Log.write(src: "app", event: "activity_token", fields: [
            "id": activity.id,
            "routeName": activity.attributes.routeName,
            "token": hex,
        ])
    }

    private func refreshCount() {
        liveCount = Activity<CommuteActivityAttributes>.activities.count
    }

    // MARK: - I3, the snapshot

    @discardableResult
    func snapshot() -> [String] {
        let all = Activity<CommuteActivityAttributes>.activities
        var lines: [String] = []
        for a in all {
            let line = "\(a.attributes.routeName) [\(a.activityState)] \(a.content.state.headline)"
            lines.append(line)
            S4Log.write(src: "app", event: "snapshot", fields: [
                "id": a.id,
                "routeName": a.attributes.routeName,
                "state": "\(a.activityState)",
                "headline": a.content.state.headline,
                "updatedAtDecoded": ISO8601DateFormatter().string(from: a.content.state.updatedAt),
                "hasToken": a.pushToken == nil ? "no" : "yes",
            ])
        }
        S4Log.write(src: "app", event: "snapshot_done", fields: ["count": String(all.count)])
        refreshCount()
        return lines
    }

    // MARK: - Local lifecycle

    func startLocally(routeName: String = "CR-Worcester",
                      headline: String = "Local start — no push involved",
                      staleAfter: TimeInterval? = nil) {
        let auth = ActivityAuthorizationInfo()
        guard auth.areActivitiesEnabled else {
            model.log("cannot start: Live Activities disabled (Settings > S3 Probe > Live Activities)")
            return
        }
        let attributes = CommuteActivityAttributes(routeName: routeName, stopName: "Boston Landing")
        let initial = CommuteActivityAttributes.ContentState(
            displayStatus: "on_time",
            headline: headline,
            minutesToDeparture: 12)
        do {
            let activity = try Activity.request(
                attributes: attributes,
                content: .init(state: initial,
                               staleDate: staleAfter.map { Date().addingTimeInterval($0) }),
                pushType: .token)
            current = activity
            model.setActivityState("\(activity.activityState)")
            model.log("started activity id=\(activity.id) route=\(routeName)")
            S4Log.write(src: "app", event: "local_start", fields: [
                "id": activity.id,
                "routeName": routeName,
                "staleAfter": staleAfter.map { String(Int($0)) } ?? "",
            ])
            adopt(activity, origin: "local_start")
            refreshCount()
        } catch {
            // The local path can report an error; the push path cannot report
            // anything to anyone. That asymmetry is the point of E5's 6th and
            // 7th activity.
            model.log("Activity.request FAILED: \(error.localizedDescription)")
            S4Log.write(src: "app", event: "local_start_failed", fields: [
                "routeName": routeName,
                "error": "\(error)",
                "localized": error.localizedDescription,
            ])
        }
    }

    /// E5 — walk past the documented 5-per-app cap and record where it fails and
    /// with what message.
    func startBatch(_ n: Int) {
        for i in 1...n {
            startLocally(routeName: "S4-E5-\(i)", headline: "concurrency probe \(i)")
        }
        model.log("startBatch(\(n)) done — \(liveCount) live")
    }

    /// E10 — deliberately set a stale date, to test whether the loading/progress
    /// overlay the human observed is iOS's staleness affordance. The probe's
    /// local start passes `staleDate: nil`, so an explicit one is the only way
    /// to tell whether that overlay is staleness or something else.
    func startWithStaleDate(seconds: TimeInterval) {
        startLocally(routeName: "S4-E10-stale\(Int(seconds))",
                     headline: "stale in \(Int(seconds))s",
                     staleAfter: seconds)
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
            S4Log.write(src: "app", event: "local_end", fields: ["id": activity.id])
            current = nil
            refreshCount()
        }
    }

    /// Leave the device clean for S5 — including activities this app did not
    /// start, which is the only way to clear a push-started card without its
    /// per-activity token.
    func endAll() {
        let all = Activity<CommuteActivityAttributes>.activities
        model.log("ending all \(all.count) activities")
        Task {
            for a in all {
                await a.end(nil, dismissalPolicy: .immediate)
                S4Log.write(src: "app", event: "end_all", fields: ["id": a.id])
            }
            current = nil
            refreshCount()
            model.log("endAll complete — \(liveCount) live")
        }
    }

    private func shortTime() -> String {
        let f = DateFormatter()
        f.timeStyle = .medium
        return f.string(from: .now)
    }
}
