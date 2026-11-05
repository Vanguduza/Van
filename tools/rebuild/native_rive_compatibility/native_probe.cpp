// Native compatibility probe. The original Rive core owns import, animation,
// skeleton, constraints and skinning. This Cairo transport draws its output;
// it is NOT the Android/JNI/Skia/PLS renderer and grants no admission.
#include "rive/file.hpp"
#include "rive/node.hpp"
#include "rive/animation/state_machine_instance.hpp"
#include "rive/animation/state_machine_input_instance.hpp"
#include "rive/animation/animation_state.hpp"
#include "rive/animation/linear_animation.hpp"
#include "rive/math/raw_path.hpp"
#include "rive/math/path_types.hpp"
#include <cairo.h>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
using namespace rive;
static void require(bool ok,const char* message){if(!ok)throw std::runtime_error(message);}
static cairo_matrix_t matrix(const Mat2D& m){return {m[0],m[1],m[2],m[3],m[4],m[5]};}
static cairo_operator_t blend(BlendMode mode){
 switch(mode){
  case BlendMode::srcOver:return CAIRO_OPERATOR_OVER;
  case BlendMode::screen:return CAIRO_OPERATOR_SCREEN;
  case BlendMode::overlay:return CAIRO_OPERATOR_OVERLAY;
  case BlendMode::darken:return CAIRO_OPERATOR_DARKEN;
  case BlendMode::lighten:return CAIRO_OPERATOR_LIGHTEN;
  case BlendMode::colorDodge:return CAIRO_OPERATOR_COLOR_DODGE;
  case BlendMode::colorBurn:return CAIRO_OPERATOR_COLOR_BURN;
  case BlendMode::hardLight:return CAIRO_OPERATOR_HARD_LIGHT;
  case BlendMode::softLight:return CAIRO_OPERATOR_SOFT_LIGHT;
  case BlendMode::difference:return CAIRO_OPERATOR_DIFFERENCE;
  case BlendMode::exclusion:return CAIRO_OPERATOR_EXCLUSION;
  case BlendMode::multiply:return CAIRO_OPERATOR_MULTIPLY;
  case BlendMode::hue:return CAIRO_OPERATOR_HSL_HUE;
  case BlendMode::saturation:return CAIRO_OPERATOR_HSL_SATURATION;
  case BlendMode::color:return CAIRO_OPERATOR_HSL_COLOR;
  case BlendMode::luminosity:return CAIRO_OPERATOR_HSL_LUMINOSITY;
 }
 throw std::runtime_error("unsupported native blend mode");
}
class CpuBuffer final:public RenderBuffer{
public:
 std::vector<uint8_t> bytes;
 CpuBuffer(RenderBufferType t,RenderBufferFlags f,size_t n):RenderBuffer(t,f,n),bytes(n){require(n<=16*1024*1024,"render buffer limit");}
protected:void* onMap()override{return bytes.data();}void onUnmap()override{}
};
class CpuShader final:public RenderShader{
public:cairo_pattern_t* value;explicit CpuShader(cairo_pattern_t* v):value(v){require(cairo_pattern_status(v)==CAIRO_STATUS_SUCCESS,"shader");}~CpuShader()override{cairo_pattern_destroy(value);}
};
class CpuPath final:public RenderPath{
public:
 cairo_surface_t* surface=cairo_recording_surface_create(CAIRO_CONTENT_COLOR_ALPHA,nullptr);
 cairo_t* context=cairo_create(surface);FillRule rule=FillRule::nonZero;
 ~CpuPath()override{cairo_destroy(context);cairo_surface_destroy(surface);}
 void rewind()override{cairo_new_path(context);}void fillRule(FillRule v)override{rule=v;}
 void addRenderPath(RenderPath* raw,const Mat2D& value)override{
  auto* p=dynamic_cast<CpuPath*>(raw);require(p,"native path adapter identity");Mat2D inverse;if(!value.invert(&inverse))return;
  auto* path=cairo_copy_path(p->context);auto m=matrix(value);cairo_save(context);cairo_transform(context,&m);cairo_append_path(context,path);cairo_restore(context);cairo_path_destroy(path);
 }
 void moveTo(float x,float y)override{cairo_move_to(context,x,y);}void lineTo(float x,float y)override{cairo_line_to(context,x,y);}
 void cubicTo(float a,float b,float c,float d,float e,float f)override{cairo_curve_to(context,a,b,c,d,e,f);}void close()override{cairo_close_path(context);}
 void apply(cairo_t* target)const{auto* p=cairo_copy_path(context);cairo_new_path(target);cairo_append_path(target,p);cairo_path_destroy(p);cairo_set_fill_rule(target,rule==FillRule::evenOdd?CAIRO_FILL_RULE_EVEN_ODD:CAIRO_FILL_RULE_WINDING);}
};
class CpuPaint final:public RenderPaint{
public:ColorInt rgba=0xff000000;RenderPaintStyle mode=RenderPaintStyle::fill;float width=1;StrokeJoin strokeJoin=StrokeJoin::miter;StrokeCap strokeCap=StrokeCap::butt;BlendMode compositing=BlendMode::srcOver;rcp<RenderShader> gradient;
 void color(ColorInt v)override{rgba=v;}void style(RenderPaintStyle v)override{mode=v;}void thickness(float v)override{width=v;}
 void join(StrokeJoin v)override{strokeJoin=v;}void cap(StrokeCap v)override{strokeCap=v;}void blendMode(BlendMode v)override{compositing=v;}void shader(rcp<RenderShader> v)override{gradient=std::move(v);}void invalidateStroke()override{}
 void feather(float v)override{require(std::abs(v)<1e-6,"feather unsupported by diagnostic CPU transport");}
 void apply(cairo_t* c)const{
  cairo_set_operator(c,blend(compositing));cairo_set_line_width(c,width);cairo_set_line_join(c,static_cast<cairo_line_join_t>(strokeJoin));cairo_set_line_cap(c,static_cast<cairo_line_cap_t>(strokeCap));
  if(gradient){auto* g=dynamic_cast<CpuShader*>(gradient.get());require(g,"shader type");cairo_set_source(c,g->value);}
  else cairo_set_source_rgba(c,colorRed(rgba)/255.,colorGreen(rgba)/255.,colorBlue(rgba)/255.,colorAlpha(rgba)/255.);
 }
};
class CpuImage final:public RenderImage{
public:cairo_surface_t* surface;explicit CpuImage(cairo_surface_t* s):surface(s){m_Width=cairo_image_surface_get_width(s);m_Height=cairo_image_surface_get_height(s);require(m_Width>0&&m_Height>0&&m_Width<=8192&&m_Height<=8192,"decoded image bounds");}~CpuImage()override{cairo_surface_destroy(surface);}
};
class CpuFactory final:public Factory{
public:
 size_t decodedImages=0,decodedPixels=0;
 rcp<RenderBuffer> makeRenderBuffer(RenderBufferType t,RenderBufferFlags f,size_t n)override{return make_rcp<CpuBuffer>(t,f,n);}
 static rcp<RenderShader> gradient(cairo_pattern_t* p,const ColorInt* colors,const float* stops,size_t count){
  require(count<=256,"gradient stop bound");for(size_t i=0;i<count;i++)cairo_pattern_add_color_stop_rgba(p,stops[i],colorRed(colors[i])/255.,colorGreen(colors[i])/255.,colorBlue(colors[i])/255.,colorAlpha(colors[i])/255.);
  cairo_pattern_set_extend(p,CAIRO_EXTEND_PAD);return make_rcp<CpuShader>(p);
 }
 rcp<RenderShader> makeLinearGradient(float x,float y,float a,float b,const ColorInt* c,const float* s,size_t n)override{return gradient(cairo_pattern_create_linear(x,y,a,b),c,s,n);}
 rcp<RenderShader> makeRadialGradient(float x,float y,float r,const ColorInt* c,const float* s,size_t n)override{return gradient(cairo_pattern_create_radial(x,y,0,x,y,r),c,s,n);}
 rcp<RenderPath> makeEmptyRenderPath()override{return make_rcp<CpuPath>();}
 rcp<RenderPath> makeRenderPath(RawPath& raw,FillRule rule)override{
  auto p=make_rcp<CpuPath>();p->rule=rule;
  for(auto item:raw){auto verb=std::get<0>(item);auto v=std::get<1>(item);
   switch(verb){
    case PathVerb::move:p->moveTo(v[0].x,v[0].y);break;
    case PathVerb::line:p->lineTo(v[1].x,v[1].y);break;
    case PathVerb::quad:p->cubicTo(v[0].x+2*(v[1].x-v[0].x)/3,v[0].y+2*(v[1].y-v[0].y)/3,v[2].x+2*(v[1].x-v[2].x)/3,v[2].y+2*(v[1].y-v[2].y)/3,v[2].x,v[2].y);break;
    case PathVerb::cubic:p->cubicTo(v[1].x,v[1].y,v[2].x,v[2].y,v[3].x,v[3].y);break;
    case PathVerb::close:p->close();break;
   }
  }return p;
 }
 rcp<RenderPaint> makeRenderPaint()override{return make_rcp<CpuPaint>();}
 rcp<RenderImage> decodeImage(Span<const uint8_t> data)override{
  struct Reader{Span<const uint8_t> bytes;size_t position=0;};Reader reader{data};
  auto callback=[](void* opaque,unsigned char* target,unsigned int length)->cairo_status_t{auto& r=*static_cast<Reader*>(opaque);if(length>r.bytes.size()-r.position)return CAIRO_STATUS_READ_ERROR;std::memcpy(target,r.bytes.data()+r.position,length);r.position+=length;return CAIRO_STATUS_SUCCESS;};
  auto* surface=cairo_image_surface_create_from_png_stream(callback,&reader);
  if(cairo_surface_status(surface)!=CAIRO_STATUS_SUCCESS){cairo_surface_destroy(surface);throw std::runtime_error("embedded PNG decode failed");}
  auto image=make_rcp<CpuImage>(surface);decodedImages++;decodedPixels+=image->width()*image->height();return image;
 }
};
class CpuRenderer final:public Renderer{
public:
 cairo_surface_t* surface;cairo_t* context;int depth=0;bool emptyTransform=false;std::vector<bool> savedEmpty;size_t paths=0,images=0,triangles=0;
 CpuRenderer(int w,int h):surface(cairo_image_surface_create(CAIRO_FORMAT_ARGB32,w,h)),context(cairo_create(surface)){require(cairo_status(context)==CAIRO_STATUS_SUCCESS,"surface creation");}
 ~CpuRenderer()override{cairo_destroy(context);cairo_surface_destroy(surface);}
 void save()override{depth++;savedEmpty.push_back(emptyTransform);cairo_save(context);}void restore()override{require(depth>0,"unbalanced native renderer restore");depth--;emptyTransform=savedEmpty.back();savedEmpty.pop_back();cairo_restore(context);}
 void transform(const Mat2D& value)override{if(emptyTransform)return;Mat2D inv;if(!value.invert(&inv)){emptyTransform=true;return;}auto m=matrix(value);cairo_transform(context,&m);}
 void drawPath(RenderPath* raw,RenderPaint* paint)override{if(emptyTransform)return;auto* p=dynamic_cast<CpuPath*>(raw);auto* color=dynamic_cast<CpuPaint*>(paint);require(p&&color,"path/paint identity");cairo_save(context);p->apply(context);color->apply(context);if(color->mode==RenderPaintStyle::fill)cairo_fill(context);else cairo_stroke(context);cairo_restore(context);paths++;}
 void clipPath(RenderPath* raw)override{if(emptyTransform)return;auto* p=dynamic_cast<CpuPath*>(raw);require(p,"clip identity");p->apply(context);cairo_clip(context);}
 void drawImage(const RenderImage* raw,BlendMode mode,float opacity)override{
  if(emptyTransform||opacity<=0)return;auto* im=dynamic_cast<const CpuImage*>(raw);require(im,"image identity");cairo_save(context);cairo_set_operator(context,blend(mode));cairo_set_source_surface(context,im->surface,0,0);cairo_pattern_set_filter(cairo_get_source(context),CAIRO_FILTER_BILINEAR);cairo_paint_with_alpha(context,opacity);cairo_restore(context);images++;
 }
 void drawImageMesh(const RenderImage* raw,rcp<RenderBuffer> v,rcp<RenderBuffer> uv,rcp<RenderBuffer> idx,uint32_t count,uint32_t n,BlendMode mode,float opacity)override{
  if(emptyTransform||opacity<=0)return;auto* im=dynamic_cast<const CpuImage*>(raw);auto* vb=dynamic_cast<CpuBuffer*>(v.get());auto* ub=dynamic_cast<CpuBuffer*>(uv.get());auto* ib=dynamic_cast<CpuBuffer*>(idx.get());require(im&&vb&&ub&&ib,"mesh buffers");
  require(vb->bytes.size()==count*sizeof(Vec2D)&&ub->bytes.size()==count*sizeof(Vec2D)&&ib->bytes.size()==n*sizeof(uint16_t)&&n%3==0,"native mesh counts");
  const Vec2D* points=reinterpret_cast<const Vec2D*>(vb->bytes.data());const Vec2D* tex=reinterpret_cast<const Vec2D*>(ub->bytes.data());const uint16_t* indices=reinterpret_cast<const uint16_t*>(ib->bytes.data());
  for(uint32_t i=0;i<n;i+=3){
   require(indices[i]<count&&indices[i+1]<count&&indices[i+2]<count,"mesh index bound");
   Vec2D p[3],t[3];for(int j=0;j<3;j++){p[j]=points[indices[i+j]];auto q=tex[indices[i+j]];t[j]={q.x*im->width(),q.y*im->height()};}
   Mat2D source(t[1].x-t[0].x,t[1].y-t[0].y,t[2].x-t[0].x,t[2].y-t[0].y,t[0].x,t[0].y),inverse;
   if(!source.invert(&inverse))continue;
   Mat2D dest(p[1].x-p[0].x,p[1].y-p[0].y,p[2].x-p[0].x,p[2].y-p[0].y,p[0].x,p[0].y);
   auto m=matrix(Mat2D::multiply(dest,inverse));cairo_save(context);cairo_new_path(context);cairo_move_to(context,p[0].x,p[0].y);cairo_line_to(context,p[1].x,p[1].y);cairo_line_to(context,p[2].x,p[2].y);cairo_close_path(context);cairo_clip(context);cairo_transform(context,&m);cairo_set_operator(context,blend(mode));cairo_set_source_surface(context,im->surface,0,0);cairo_pattern_set_filter(cairo_get_source(context),CAIRO_FILTER_BILINEAR);cairo_paint_with_alpha(context,opacity);cairo_restore(context);triangles++;
  }
 }
 size_t capture(const std::string& filename){require(depth==0,"unbalanced final save/restore");require(cairo_status(context)==CAIRO_STATUS_SUCCESS,cairo_status_to_string(cairo_status(context)));cairo_surface_flush(surface);size_t count=0;auto* bytes=cairo_image_surface_get_data(surface);int w=cairo_image_surface_get_width(surface),h=cairo_image_surface_get_height(surface),stride=cairo_image_surface_get_stride(surface);for(int y=0;y<h;y++)for(int x=0;x<w;x++)if(bytes[y*stride+x*4+3]>32)count++;require(cairo_surface_write_to_png(surface,filename.c_str())==CAIRO_STATUS_SUCCESS,"PNG capture failed");return count;}
};
struct ProbeScene{
 std::unique_ptr<ArtboardInstance> board;std::unique_ptr<StateMachineInstance> machine;std::vector<std::string> events;
 explicit ProbeScene(File& file){board=file.artboardNamed("Van");require(bool(board),"native Van artboard missing");machine=board->stateMachineNamed("VanRuntime");require(bool(machine),"native VanRuntime missing");step(1);}
 void set(const char* key,float value){auto* input=machine->getNumber(key);require(input,"missing native numeric input");input->value(value);}
 void flag(const char* key,bool value){auto* input=machine->getBool(key);require(input,"missing native bool input");input->value(value);}
 void step(int frames){for(int i=0;i<frames;i++){machine->advanceAndApply(1.f/60.f);for(size_t j=0;j<machine->stateChangedCount();j++){auto* changed=machine->stateChangedByIndex(j);if(changed&&changed->is<AnimationState>()){auto* animation=changed->as<AnimationState>()->animation();if(animation)events.push_back(animation->name());}}}}
 Node& node(const std::string& name){auto* n=board->find<Node>(name);require(n,"missing native named node");return *n;}
};
static std::string escape(const std::string& s){std::string o;for(char c:s){if(c=='"'||c=='\\')o+='\\';o+=c;}return o;}
static void emitNodes(ProbeScene& s){
 std::vector<std::string> names={"rig_shoulder_l","rig_elbow_l","rig_wrist_l","rig_shoulder_r","rig_elbow_r","rig_wrist_r","rig_nod","rig_orb","rig_eyelid_l","rig_eyelid_r","rig_mouth_open","r5_live_point_target","r5_soft_smile","r5_head_gaze_left_right","r5_head_gaze_up_down"};
 for(const auto& side:{"l","r"})for(const auto& part:{"index_prox","index_tip","thumb","middle","ring","little"})names.push_back(std::string("rig_")+part+"_"+side);
 std::cout<<"\"nodes\":{";bool first=true;
 for(const auto& name:names){auto* n=s.board->find<Node>(name);if(!n)continue;if(!first)std::cout<<',';first=false;const auto& m=n->worldTransform();std::cout<<'"'<<name<<"\":{\"x\":"<<m.tx()<<",\"y\":"<<m.ty()<<",\"rotation\":"<<n->rotation()<<",\"scaleX\":"<<n->scaleX()<<",\"scaleY\":"<<n->scaleY()<<'}';}
 std::cout<<"},\"events\":[";for(size_t i=0;i<s.events.size();i++){if(i)std::cout<<',';std::cout<<'"'<<escape(s.events[i])<<'"';}std::cout<<']';
}
int main(int argc,char**argv){
 try{
  require(argc==3||argc==4,"Usage: native_probe exact-candidate.riv new-output-directory [control]");std::ifstream input(argv[1],std::ios::binary);require(bool(input),"candidate unreadable");std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(input)),{});require(bytes.size()<=8*1024*1024,"candidate byte limit");
  CpuFactory factory;ImportResult result=ImportResult::malformed;auto file=File::import(Span<const uint8_t>(bytes.data(),bytes.size()),&factory,&result);
  require(file&&result==ImportResult::success,"PINNED_ANDROID_CORE_REJECTED_CANDIDATE");std::cout<<"{\"kind\":\"import\",\"result\":\"success\",\"artboards\":"<<file->artboardCount()<<",\"decoded_pngs\":"<<factory.decodedImages<<",\"decoded_pixels\":"<<factory.decodedPixels<<",\"runtime_major\":"<<File::majorVersion<<",\"runtime_minor\":"<<File::minorVersion<<"}\n";
  if(argc==4){
   require(std::string(argv[3])=="control","unknown mode");auto control=file->artboardDefault();require(bool(control),"positive control artboard");auto scene=control->defaultScene();if(scene){for(int i=0;i<60;i++)scene->advanceAndApply(1.f/60.f);}else control->advance(1.f);
   CpuRenderer renderer(593,593);renderer.align(Fit::contain,Alignment::center,AABB(0,0,593,593),control->bounds());control->draw(&renderer);auto visible=renderer.capture(std::string(argv[2])+"/positive-control.png");std::cout<<"{\"kind\":\"control\",\"visible_pixels\":"<<visible<<",\"paths\":"<<renderer.paths<<",\"images\":"<<renderer.images<<",\"triangles\":"<<renderer.triangles<<"}\n";require(visible>1000,"empty positive control render");return 0;
  }
  {ProbeScene s(*file);std::cout<<"{\"kind\":\"surface\",\"inputs\":[";for(size_t i=0;i<s.machine->inputCount();i++){if(i)std::cout<<',';std::cout<<'"'<<escape(s.machine->input(i)->name())<<'"';}std::cout<<"],\"animations\":"<<s.board->animationCount()<<"}\n";}
  auto record=[&](ProbeScene& scene,const std::string& label,bool image){std::cout<<"{\"kind\":\"sample\",\"label\":\""<<label<<"\",";emitNodes(scene);if(image){CpuRenderer renderer(593,593);scene.board->draw(&renderer);size_t visible=renderer.capture(std::string(argv[2])+"/"+label+".png");std::cout<<",\"visible_pixels\":"<<visible<<",\"draw_paths\":"<<renderer.paths<<",\"draw_images\":"<<renderer.images<<",\"mesh_triangles\":"<<renderer.triangles;}std::cout<<"}\n";};
  for(int state=0;state<18;state++){ProbeScene s(*file);s.set("state",float(state));s.step(60);record(s,"state-"+std::to_string(state),true);}
  const int ms[]={0,1400,650,1200,1200,1200,1200,1200,1800,1000,900,1100,1500,700,700,1400,1800,1500,1300,1000,1100,1200,650,1300,1500,1000,1500};
  for(int code=1;code<=26;code++){ProbeScene s(*file);s.set("state",2);s.set("attention_x",.8f);s.set("attention_y",-.6f);s.step(20);s.set("action_code",float(code));s.step(int(std::lround(ms[code]*.6*.06)));record(s,"action-"+std::to_string(code),true);s.set("action_code",0);s.step(6);record(s,"clear-"+std::to_string(code),false);}
  for(int i=0;i<16;i++){ProbeScene s(*file);float angle=i*6.28318530718f/16;s.set("state",2);s.set("attention_x",std::cos(angle));s.set("attention_y",std::sin(angle));s.step(20);s.set("action_code",7);s.step(42);record(s,"target-"+std::to_string(i),false);}
  {ProbeScene s(*file);s.set("state",2);record(s,"orb-start",true);s.step(711);record(s,"orb-other-side",true);s.step(711);record(s,"orb-return",true);}
  for(int shape=0;shape<=4;shape++){ProbeScene s(*file);s.set("state",9);s.flag("speaking",true);s.set("mouth_open",.8f);s.set("viseme",float(shape));s.step(30);record(s,"mouth-"+std::to_string(shape),true);}
  {ProbeScene s(*file);s.set("state",2);s.step(20);auto* wave=s.machine->getTrigger("wave");require(wave,"wave trigger missing");wave->fire();s.step(30);record(s,"legacy-wave",true);s.step(90);record(s,"legacy-wave-clear",false);}
  {ProbeScene s(*file);s.set("state",17);s.step(60);record(s,"sleep-held",false);s.step(2160);record(s,"sleep-after-blink-cycle",false);s.set("state",2);s.step(20);record(s,"woken",false);}
  {ProbeScene s(*file);s.set("state",2);s.step(20);s.set("action_code",1);s.step(25);s.set("state",16);s.set("action_code",9);s.step(6);record(s,"urgent-preemption",false);}
  {ProbeScene s(*file);s.set("state",2);s.set("attention_x",1);s.step(20);s.set("action_code",7);s.step(24);record(s,"retarget-initial",false);const float dirs[][2]={{.6f,-.8f},{-.8f,.6f},{0,1}};for(int i=0;i<3;i++){s.set("attention_x",dirs[i][0]);s.set("attention_y",dirs[i][1]);s.step(5);record(s,"retarget-"+std::to_string(i),false);}}
  for(int code:{-1,99}){ProbeScene s(*file);s.set("state",2);s.set("action_code",1);s.step(30);s.set("action_code",float(code));s.step(6);record(s,"invalid-action-"+std::to_string(code),false);}
  {ProbeScene a(*file),b(*file);a.set("state",2);b.set("state",2);a.step(250);b.step(250);b.set("state",9);b.set("action_code",15);a.step(400);b.step(400);record(a,"orbit-control",false);record(b,"orbit-context-changed",false);}
  {ProbeScene s(*file);s.set("state",2);std::vector<int> peaks;bool wasClosed=false;for(int f=0;f<2160;f++){s.step(1);bool closed=s.node("rig_eyelid_l").scaleY()>.9f;if(closed&&!wasClosed)peaks.push_back(f);wasClosed=closed;}std::cout<<"{\"kind\":\"blink\",\"peaks\":[";for(size_t i=0;i<peaks.size();i++){if(i)std::cout<<',';std::cout<<peaks[i];}std::cout<<"]}\n";}
  std::cout<<"{\"kind\":\"terminal\",\"native_probe_completed\":true,\"android_device\":false,\"renderer\":\"custom Cairo transport over unmodified exact Android9.13.10 C++ core\"}\n";
  return 0;
 }catch(const std::exception& e){std::cerr<<"NATIVE_PROBE_ERROR "<<e.what()<<'\n';return 1;}
}
