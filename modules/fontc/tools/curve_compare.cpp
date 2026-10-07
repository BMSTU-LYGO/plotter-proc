#include "fontc/pfc.hpp"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <string_view>

namespace {
struct Stats { std::size_t points{}, segments{}, below_005{}, below_010{}; double length_mm{}, seconds{}; };
Stats measure(const fontc::CompiledGlyph* glyph,double mm_per_unit,bool adaptive) {
    Stats result;
    if(!glyph) return result;
    for(const auto& stroke:glyph->strokes) {
        result.points+=stroke.points.size();
        for(std::size_t i=1;i<stroke.points.size();++i) {
            const auto& a=stroke.points[i-1]; const auto& b=stroke.points[i];
            const double dx=double(b.x)-a.x,dy=double(b.y)-a.y;
            const double length=std::hypot(dx,dy)*mm_per_unit;
            if(length<=0) continue;
            ++result.segments;result.length_mm+=length;
            if(length<0.05) ++result.below_005;
            if(length<0.10) ++result.below_010;
            double feed=2000;
            if(adaptive) {
                double cosine=1;
                if(i+1<stroke.points.size()) {
                    const auto& c=stroke.points[i+1];
                    const double ux=double(c.x)-b.x,uy=double(c.y)-b.y;
                    const double denominator=std::hypot(dx,dy)*std::hypot(ux,uy);
                    if(denominator>0) cosine=(dx*ux+dy*uy)/denominator;
                }
                feed=cosine<0.5?1200:cosine<0.94?2000:2700;
            }
            result.seconds+=length/feed*60;
        }
    }
    return result;
}
void row(std::string_view label,const fontc::PfcFont& old_font,const fontc::PfcFont& new_font,
         const std::vector<std::uint32_t>& codes) {
    Stats old{},now{};
    const double old_scale=5.0/old_font.metrics().units_per_em;
    const double new_scale=5.0/new_font.metrics().units_per_em;
    for(auto code:codes) {
        const Stats a=measure(old_font.find(code),old_scale,false);
        const Stats b=measure(new_font.find(code),new_scale,true);
        old.points+=a.points;old.segments+=a.segments;old.length_mm+=a.length_mm;old.seconds+=a.seconds;
        now.points+=b.points;now.segments+=b.segments;now.length_mm+=b.length_mm;now.seconds+=b.seconds;
        old.below_005+=a.below_005;old.below_010+=a.below_010;
        now.below_005+=b.below_005;now.below_010+=b.below_010;
    }
    std::cout<<"| "<<label<<" | "<<old.points<<" | "<<now.points<<" | "
             <<old.segments<<" | "<<now.segments<<" | "
             <<old.length_mm<<" | "<<now.length_mm<<" | "
             <<old.seconds<<" | "<<now.seconds<<" |\n";
}
}
int main(int argc,char** argv) {
    if(argc!=3) {std::cerr<<"Usage: curve_compare old.pfc new.pfc\n";return 2;}
    const auto old_font=fontc::PfcFont::load(argv[1]);
    const auto new_font=fontc::PfcFont::load(argv[2]);
    std::cout<<"| glyph | points_before | points_after | gcode_segments_before | gcode_segments_after | draw_length_before_mm | draw_length_after_mm | estimated_execution_time_before_s | estimated_execution_time_after_s |\n"
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|\n";
    for(const auto [label,code]: {std::pair{"и",0x0438U},{"м",0x043CU},{"ш",0x0448U},
        {"ж",0x0436U},{"о",0x043EU},{"а",0x0430U},{"ф",0x0444U},{"д",0x0434U}})
        row(label,old_font,new_font,{code});
    row("текст",old_font,new_font,{0x041FU,0x0440U,0x0438U,0x0432U,0x0435U,0x0442U,
        0x0020U,0x043CU,0x0438U,0x0440U,0x0021U});
    Stats old{},now{};
    for(const auto& glyph:old_font.glyphs()) {
        const auto one=measure(&glyph,5.0/old_font.metrics().units_per_em,false);
        old.segments+=one.segments;old.below_005+=one.below_005;old.below_010+=one.below_010;
    }
    for(const auto& glyph:new_font.glyphs()) {
        const auto one=measure(&glyph,5.0/new_font.metrics().units_per_em,true);
        now.segments+=one.segments;now.below_005+=one.below_005;now.below_010+=one.below_010;
    }
    std::cout<<"segments <0.05 mm: "<<old.below_005<<" -> "<<now.below_005
             <<"; <0.10 mm: "<<old.below_010<<" -> "<<now.below_010<<'\n';
}
