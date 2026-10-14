// Authenticated composition for the fixed one-leg Wi-Fi registration runtime.
#pragma once
#include "characterization_authenticated_web.h"
#include "registration_ladder_wifi_routes.h"

namespace rocell_diag {
template<class Crypto,class Services,class Web> class RegistrationLadderWifiComposition {
  using Gate=CharacterizationRequestAuth<Crypto>;
  using AuthWeb=CharacterizationAuthenticatedWeb<Gate,Web>;
  using Routes=RegistrationLadderWifiRoutes<Services,AuthWeb>;
 public:
  RegistrationLadderWifiComposition(Crypto& crypto,Services& services,Web& raw_web,
      const uint8_t (&key)[32],const uint8_t (&boot)[16])
      :gate_(crypto,key,boot),web_(gate_,raw_web),routes_(services,web_,boot){}
  RegistrationLadderWifiComposition(const RegistrationLadderWifiComposition&)=delete;
  RegistrationLadderWifiComposition& operator=(const RegistrationLadderWifiComposition&)=delete;
  void register_routes(){
    if(registered_)return;registered_=true;web_.collect_headers();routes_.register_routes();
  }
  void poll(){routes_.poll();}
 private:
  Gate gate_;AuthWeb web_;Routes routes_;bool registered_=false;
};
}
