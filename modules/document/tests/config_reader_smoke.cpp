#include "plotter/doc/config_reader.hpp"

#include <cassert>

using namespace plotter::doc;
int main() {
    const auto a5 = load_pipeline_config("configs/layout.yaml", "configs/machine.yaml", "A5");
    assert(a5.page.width.value == 148.0 && a5.page.height.value == 210.0);
    assert(a5.machine.invert_y && a5.machine.page_origin.x.value == 10.0);
    assert(a5.machine.feedrate.draw_mm_min == 6000.0);
    assert(a5.machine.keep_out.size() == 2);
    assert(a5.machine.keep_out.front().radius.value == 3.0);
    const auto a4 = load_pipeline_config("configs/layout.yaml", "configs/machine-a4.yaml", "A4");
    assert(a4.page.width.value == 210.0 && a4.page.height.value == 297.0);
    assert(a4.page.margins.left.value == 10.0 && a4.page.margins.right.value == 10.0);
    assert(a4.page.margins.top.value == 10.0 && a4.page.margins.bottom.value == 10.0);
    assert(a4.machine.workspace.min_x.value == 0.0 && a4.machine.workspace.max_x.value == 225.0);
    assert(a4.machine.workspace.min_y.value == 55.0 && a4.machine.workspace.max_y.value == 355.0);
    assert(a4.machine.page_origin.x.value == 5.0 && a4.machine.page_origin.y.value == 55.0);
    assert(a4.machine.keep_out.empty());
    assert(a4.machine.feedrate.draw_mm_min == 6000.0);
}
