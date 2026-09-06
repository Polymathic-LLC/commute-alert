import ActivityKit
import SwiftUI
import WidgetKit

/// The one Live Activity. Presentation is intentionally plain — S4 measures
/// lifecycle and budget, not visual design.
///
/// S4 addition: every render calls `S4Log.render`, which appends a line to the
/// shared App Group container. This is instrument I1 (see PROTOCOL.md), and it
/// is the only way to observe whether a push actually landed during a run too
/// long or too fast for a person to watch. It runs in the widget extension
/// process, which is why it cannot report through `ProbeModel`.
///
/// Calling a side-effecting function from a SwiftUI body is not something to do
/// in production code. It is done here deliberately and knowingly: the view body
/// is the only code the system runs when it applies a content-state update, so
/// it is the only place an update can be observed without keeping the app alive
/// — and keeping the app alive would change the thing being measured.
struct CommuteLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: CommuteActivityAttributes.self) { context in
            lockScreen(context)
                .activityBackgroundTint(Color.black.opacity(0.35))
                .activitySystemActionForegroundColor(.white)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Text(context.state.displayStatus).font(.caption).bold()
                }
                DynamicIslandExpandedRegion(.trailing) {
                    if let minutes = context.state.minutesToDeparture {
                        Text("\(minutes) min").font(.caption).monospacedDigit()
                    }
                }
                DynamicIslandExpandedRegion(.bottom) {
                    Text(context.state.headline).font(.footnote)
                }
            } compactLeading: {
                compactLeading(context)
            } compactTrailing: {
                if let minutes = context.state.minutesToDeparture {
                    Text("\(minutes)m").monospacedDigit()
                }
            } minimal: {
                Text("🚆")
            }
        }
    }

    // MARK: - Surfaces (each logs its own render)

    /// Not `@ViewBuilder`: it needs a statement before the view, and the body is
    /// a single view anyway.
    private func lockScreen(_ context: ActivityViewContext<CommuteActivityAttributes>) -> some View {
        log(context, surface: "lock")
        return VStack(alignment: .leading, spacing: 4) {
            Text("\(context.attributes.routeName) · \(context.attributes.stopName)")
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(context.state.headline)
                .font(.headline)
            HStack {
                Text(context.state.displayStatus)
                Spacer()
                if let minutes = context.state.minutesToDeparture {
                    Text("\(minutes) min").monospacedDigit()
                }
            }
            .font(.subheadline)
            Text("v\(context.state.v) · \(context.state.updatedAt.formatted(date: .omitted, time: .standard))")
                .font(.caption2)
                .foregroundStyle(.tertiary)
        }
        .padding()
    }

    /// A second capture channel. The Lock Screen surface may not be rendered
    /// while the screen is off; the Dynamic Island compact surface is rendered
    /// under different conditions. Two surfaces means a missed render on one
    /// does not silently become a missed update.
    private func compactLeading(_ context: ActivityViewContext<CommuteActivityAttributes>) -> some View {
        log(context, surface: "compact")
        return Text("🚆")
    }

    private func log(_ context: ActivityViewContext<CommuteActivityAttributes>, surface: String) {
        S4Log.render(surface: surface,
                     routeName: context.attributes.routeName,
                     stopName: context.attributes.stopName,
                     v: context.state.v,
                     displayStatus: context.state.displayStatus,
                     headline: context.state.headline,
                     minutesToDeparture: context.state.minutesToDeparture,
                     updatedAt: context.state.updatedAt)
    }
}
