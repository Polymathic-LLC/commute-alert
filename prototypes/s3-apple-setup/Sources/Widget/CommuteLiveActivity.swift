import ActivityKit
import SwiftUI
import WidgetKit

/// The one Live Activity. Presentation is intentionally plain — S4 measures
/// lifecycle and budget, not visual design.
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
                Text("🚆")
            } compactTrailing: {
                if let minutes = context.state.minutesToDeparture {
                    Text("\(minutes)m").monospacedDigit()
                }
            } minimal: {
                Text("🚆")
            }
        }
    }

    @ViewBuilder
    private func lockScreen(_ context: ActivityViewContext<CommuteActivityAttributes>) -> some View {
        VStack(alignment: .leading, spacing: 4) {
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
}
