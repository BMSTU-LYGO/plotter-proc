#include "fontc/curve_fit.hpp"
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <vector>

namespace {
void require(bool value,const char* message) { if(!value) {std::cerr<<message<<'\n';std::exit(1);} }
fontc::SkeletonGraph graph(std::vector<fontc::Point> points,bool closed=false) {
    const auto last=closed?0U:1U;
    return {{{0,points.front(),closed?std::vector<std::uint32_t>{0,0}:std::vector<std::uint32_t>{0}},
             {1,points.back(),closed?std::vector<std::uint32_t>{}:std::vector<std::uint32_t>{0}}},
            {{0,0,last,std::move(points)}}};
}
}
int main() {
    const fontc::CurveOptions options{0.2F,0.1F,0.1F,3.0F,1.5F,0.5F};
    std::vector<fontc::Point> line,arc,s_curve;
    for(int i=0;i<=100;++i) {
        const float x=static_cast<float>(i)*0.1F;
        line.push_back({x,0});
        arc.push_back({x,2.0F*std::sin(x*0.3F)});
        s_curve.push_back({x,2.0F*std::sin(x*0.6F)});
    }
    fontc::CurveStats line_stats{},arc_stats{};
    const auto fitted_line=fontc::fit_graph_edges(graph(line),options,&line_stats);
    const auto fitted_arc=fontc::fit_graph_edges(graph(arc),options,&arc_stats);
    require(fitted_line.edges[0].points.front().x==0 && fitted_line.edges[0].points.back().x==10,
            "line endpoints changed");
    require(fitted_line.edges[0].points.size()<line.size()/3,"straight line was not reduced");
    require(fitted_arc.edges[0].points.size()<arc.size(),"arc was not reduced");
    require(fitted_arc.edges[0].points.size()>fitted_line.edges[0].points.size(),"curve got fewer points than line");
    require(fontc::fit_graph_edges(graph(s_curve),options).edges[0].points.size()>2,"S curve collapsed");
    const auto corner=fontc::fit_graph_edges(graph({{0,0},{2,0},{4,0},{4,2},{4,4}}),options);
    require(corner.edges[0].points.size()>2,"sharp corner collapsed");
    const auto loop=fontc::fit_graph_edges(graph({{0,0},{2,0},{2,2},{0,2},{0,0}},true),options);
    require(loop.edges[0].points.front().x==loop.edges[0].points.back().x &&
            loop.edges[0].points.front().y==loop.edges[0].points.back().y,"closed loop opened");
    require(fontc::fit_graph_edges(graph({{0,0},{0.05F,0}}),options).edges[0].points.size()==2,
            "short stroke changed");
}
