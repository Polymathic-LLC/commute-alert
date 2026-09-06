import SwiftUI
import WidgetKit

@main
struct S3ProbeWidgetBundle: WidgetBundle {
    var body: some Widget {
        CommuteLiveActivity()
        CommuteStaticWidget()
    }
}
