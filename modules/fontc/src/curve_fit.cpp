#include "fontc/curve_fit.hpp"
#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <vector>

namespace fontc {
namespace {
Point add(Point a, Point b) { return {a.x+b.x,a.y+b.y}; }
Point sub(Point a, Point b) { return {a.x-b.x,a.y-b.y}; }
Point mul(Point a, float s) { return {a.x*s,a.y*s}; }
float length(Point a) { return std::hypot(a.x,a.y); }
Point unit(Point a) { const float n=length(a); return n>0 ? mul(a,1/n) : Point{0,0}; }
float distance(Point a,Point b) { return length(sub(a,b)); }
struct Cubic { Point a,b,c,d; };
Point eval(const Cubic& c,float t) {
    const float u=1-t;
    return add(add(mul(c.a,u*u*u),mul(c.b,3*u*u*t)),
               add(mul(c.c,3*u*t*t),mul(c.d,t*t*t)));
}
Point derivative(const Cubic& c,float t) {
    const float u=1-t;
    return add(add(mul(sub(c.b,c.a),3*u*u),mul(sub(c.c,c.b),6*u*t)),
               mul(sub(c.d,c.c),3*t*t));
}
float point_segment_distance(Point p, Point a, Point b) {
    const Point v=sub(b,a), w=sub(p,a);
    const float n=v.x*v.x+v.y*v.y;
    const float t=n>0 ? std::clamp((w.x*v.x+w.y*v.y)/n,0.0F,1.0F) : 0.0F;
    return distance(p,add(a,mul(v,t)));
}
void tessellate(const Cubic& c,float lo,float hi,Point a,Point b,
                const CurveOptions& o,std::vector<Point>& out,int depth) {
    const float mid=(lo+hi)*0.5F;
    const Point m=eval(c,mid);
    const float span=(hi-lo)/3;
    // The subcurve is inside the hull of these four controls. Their distance
    // to the chord bounds the deviation of every point on the cubic.
    const float error=std::max(point_segment_distance(add(a,mul(derivative(c,lo),span)),a,b),
        point_segment_distance(sub(b,mul(derivative(c,hi),span)),a,b));
    const float chord=distance(a,b);
    const float bend=chord>0 ? error/chord : 0;
    const float target=bend>0.12F ? o.tight_target_pixels :
                       bend>0.025F ? o.curve_target_pixels : o.straight_target_pixels;
    if (depth<18 && (error>o.max_error_pixels || chord>target) &&
        (chord>o.min_segment_pixels*1.5F || error>o.max_error_pixels)) {
        tessellate(c,lo,mid,a,m,o,out,depth+1);
        tessellate(c,mid,hi,m,b,o,out,depth+1);
    } else out.push_back(b);
}
void fit(const std::vector<Point>& p,std::size_t first,std::size_t last,
         const CurveOptions& o,std::vector<Point>& out,CurveStats& stats,int depth) {
    const Point a=p[first],d=p[last];
    const float chord=distance(a,d);
    if (last==first+1 || chord<o.min_segment_pixels) {
        out.push_back(d); return;
    }
    std::vector<float> t(last-first+1,0);
    float total=0;
    for(std::size_t i=first+1;i<=last;++i) total+=distance(p[i-1],p[i]);
    if(total<=0) { out.push_back(d); return; }
    float run=0;
    for(std::size_t i=first+1;i<=last;++i) { run+=distance(p[i-1],p[i]); t[i-first]=run/total; }
    const Point u=unit(sub(p[first+1],a)), v=unit(sub(p[last-1],d));
    float c00=0,c01=0,c11=0,x0=0,x1=0;
    for(std::size_t i=first;i<=last;++i) {
        const float z=t[i-first], q=1-z;
        const float b0=q*q*q,b1=3*q*q*z,b2=3*q*z*z,b3=z*z*z;
        const Point r=sub(p[i],add(mul(a,b0+b1),mul(d,b2+b3)));
        const Point h=mul(u,b1), k=mul(v,b2);
        c00+=h.x*h.x+h.y*h.y; c01+=h.x*k.x+h.y*k.y; c11+=k.x*k.x+k.y*k.y;
        x0+=h.x*r.x+h.y*r.y; x1+=k.x*r.x+k.y*r.y;
    }
    float alpha=chord/3,beta=chord/3;
    const float det=c00*c11-c01*c01;
    if(std::abs(det)>1e-7F) {
        const float aa=(x0*c11-x1*c01)/det,bb=(x1*c00-x0*c01)/det;
        if(aa>0 && bb>0) { alpha=std::min(aa,total); beta=std::min(bb,total); }
    }
    const Cubic curve{a,add(a,mul(u,alpha)),add(d,mul(v,beta)),d};
    float error=0; std::size_t split=first+(last-first)/2;
    for(std::size_t i=first+1;i<last;++i) {
        const float e=distance(p[i],eval(curve,t[i-first]));
        if(e>error) { error=e; split=i; }
    }
    if(error>o.fit_error_pixels && depth<18 && last-first>2) {
        fit(p,first,split,o,out,stats,depth+1);
        fit(p,split,last,o,out,stats,depth+1);
    } else {
        ++stats.bezier_segments;
        tessellate(curve,0,1,a,d,o,out,0);
    }
}
std::vector<Point> simplify(const std::vector<Point>& p,float tolerance) {
    if(p.size()<3) return p;
    std::vector<bool> keep(p.size(),false); keep.front()=keep.back()=true;
    std::vector<std::pair<std::size_t,std::size_t>> work{{0,p.size()-1}};
    while(!work.empty()) {
        auto [a,b]=work.back(); work.pop_back();
        float error=0;std::size_t split=a;
        for(std::size_t i=a+1;i<b;++i) {
            const float e=point_segment_distance(p[i],p[a],p[b]);
            if(e>error) {error=e;split=i;}
        }
        if(error>tolerance) {keep[split]=true;work.emplace_back(a,split);work.emplace_back(split,b);}
    }
    std::vector<Point> out;
    for(std::size_t i=0;i<p.size();++i) if(keep[i]) out.push_back(p[i]);
    return out;
}
}
SkeletonGraph fit_graph_edges(const SkeletonGraph& graph,const CurveOptions& options,CurveStats* stats) {
    validate_skeleton_graph(graph);
    for(float value : {options.fit_error_pixels,options.max_error_pixels,options.min_segment_pixels,
                       options.straight_target_pixels,options.curve_target_pixels,options.tight_target_pixels})
        if(!std::isfinite(value)||value<=0) throw std::invalid_argument("Curve parameters must be finite and positive");
    SkeletonGraph result=graph;
    CurveStats report{};
    for(Edge& edge:result.edges) {
        report.raw_points+=edge.points.size();
        if(edge.points.size()<3) {report.final_points+=edge.points.size();continue;}
        std::vector<Point> out{edge.points.front()};
        if(edge.a==edge.b && edge.points.size()>3) {
            const std::size_t middle=(edge.points.size()-1)/2;
            fit(edge.points,0,middle,options,out,report,0);
            fit(edge.points,middle,edge.points.size()-1,options,out,report,0);
        } else fit(edge.points,0,edge.points.size()-1,options,out,report,0);
        if(edge.a!=edge.b) out=simplify(out,options.max_error_pixels*0.5F);
        out.front()=edge.points.front();out.back()=edge.points.back();
        float drawn=0;
        for(std::size_t i=1;i<out.size();++i) drawn+=distance(out[i-1],out[i]);
        if(drawn<=0) out=edge.points;
        report.final_points+=out.size(); edge.points=std::move(out);
    }
    if(stats) *stats=report;
    validate_skeleton_graph(result);
    return result;
}
}
