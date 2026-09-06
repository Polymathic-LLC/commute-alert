import ActivityKit
import Foundation

// THROWAWAY S3 PROBE — not the production content-state contract.
//
// docs/display-contract.md deliberately leaves the real field set "Open" (it is
// blocked on trip selection + the Live Activity budget, resolved by S6 and S4).
// This struct is only rich enough to let S4 exercise updates, collapse-ids and
// the 8-hour cap without a redesign. Keep it small; do not grow it into a spec.
//
// This file is compiled into BOTH the app target and the widget extension target
// (the standard ActivityKit pattern). The two copies must stay byte-identical.
struct CommuteActivityAttributes: ActivityAttributes {
    struct ContentState: Codable, Hashable {
        /// Compatibility marker, mirrors the `v` integer described in display-contract.md.
        var v: Int
        /// A value from the display-status vocabulary, e.g. "on_time", "delayed",
        /// "monitoring_unavailable". Free-form string here on purpose.
        var displayStatus: String
        /// One human-readable line shown on the lock screen.
        var headline: String
        /// Optional so S4 can test additive/absent-field behaviour.
        var minutesToDeparture: Int?
        var updatedAt: Date

        init(v: Int = 1,
             displayStatus: String,
             headline: String,
             minutesToDeparture: Int? = nil,
             updatedAt: Date = .now) {
            self.v = v
            self.displayStatus = displayStatus
            self.headline = headline
            self.minutesToDeparture = minutesToDeparture
            self.updatedAt = updatedAt
        }
    }

    var routeName: String
    var stopName: String

    init(routeName: String, stopName: String) {
        self.routeName = routeName
        self.stopName = stopName
    }
}
