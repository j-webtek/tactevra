#include <cassert>
#include <cstdint>
#include <cstring>
#include <functional>
#include <map>
#include <string>
constexpr int HTTP_GET=0,HTTP_POST=1;
#include "registration_ladder_wifi_routes.h"

using namespace rocell_diag;

struct Services {
  bool release=true,started=false;unsigned starts=0;
  bool registration_release_digest(uint8_t (&out)[32]){
    if(!release)return false;std::memset(out,0xcd,32);return true;
  }
  const char* registration_start_once(){
    ++starts;if(started)return "ALREADY_ATTEMPTED";started=true;return "LEG_ACCEPTED";
  }
  bool registration_status(char* out,size_t size){
    std::snprintf(out,size,"{\"state\":\"%s\",\"leg\":1}",started?"MOVING":"READY");
    return true;
  }
  void registration_poll(){}
};

struct Web {
  std::map<std::string,std::function<void()>> routes;
  bool signed_request=true;std::string body,response,content_type;int status=0;
  template<class Handler>void on(const char* path,int,Handler handler){routes[path]=handler;}
  bool authenticated(){return signed_request;}
  int args(){return body.empty()?0:1;}
  std::string argName(int){return "plain";}
  std::string arg(const char*){return body;}
  void send(int code,const char* type,const char* text){status=code;content_type=type;response=text;}
};

int main(){
  Services services;Web web;uint8_t boot[16];std::memset(boot,0xab,16);
  RegistrationLadderWifiRoutes<Services,Web> routes(services,web,boot);
  routes.register_routes();routes.register_routes();assert(web.routes.size()==2);
  const std::string prefix="/rocell/registration-ladder/";
  web.routes.at(prefix+"status")();
  assert(web.status==200&&web.response=="{\"state\":\"READY\",\"leg\":1}");
  web.body="RCLW1:"+std::string(32,'a');
  for(unsigned i=0;i<16;++i)web.body[6+2*i+1]='b';
  web.body+=":1:"+std::string(64,'c');
  for(unsigned i=0;i<32;++i)web.body[42+2*i+1]='d';
  web.body+=":LIVE_NONCONTACT";
  const auto admitted=web.body;
  web.signed_request=false;web.routes.at(prefix+"leg")();
  assert(web.status==403&&services.starts==0);
  web.signed_request=true;
  auto wrong=admitted;wrong[42]='0';web.body=wrong;web.routes.at(prefix+"leg")();
  assert(web.status==409&&services.starts==0);
  web.body=admitted;web.routes.at(prefix+"leg")();
  assert(web.status==202&&web.response=="LEG_ACCEPTED"&&services.starts==1);
  web.body=admitted;web.routes.at(prefix+"leg")();
  assert(web.status==409&&web.response=="ALREADY_ATTEMPTED"&&services.starts==2);
  web.body.clear();web.routes.at(prefix+"status")();
  assert(web.status==200&&web.response=="{\"state\":\"MOVING\",\"leg\":1}");
  return 0;
}
