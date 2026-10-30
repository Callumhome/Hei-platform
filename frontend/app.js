(() => {
  const $ = (id) => document.getElementById(id);
  const forms = ["login-form","register-form","verify-form","forgot-form","reset-form"];
  const tokenStore = sessionStorage;
  let currentMode = "login";
  let household = null;

  function notice(message, error = false, target = "auth-notice") {
    const el = $(target); el.textContent = message; el.classList.toggle("error", error); el.hidden = false;
  }
  function hideNotice(target = "auth-notice") { $(target).hidden = true; }
  function showSuccess(title, copy, action = "Back to sign in") {
    forms.forEach(id => $(id).hidden = true);
    $("auth-success").hidden = false; $("success-title").textContent = title; $("success-copy").textContent = copy; $("success-action").textContent = action;
    $("auth-switch").hidden = true;
  }
  function setMode(mode) {
    currentMode = mode;
    forms.forEach(id => $(id).hidden = true);
    $("auth-success").hidden = true; $("auth-switch").hidden = true; hideNotice();
    const config = {
      login: ["ACCOUNT ACCESS","Welcome back","Sign in to open your energy overview.","login-form"],
      register: ["GET STARTED","Create your HEI account","Set up a secure account for your household energy data.","register-form"],
      verify: ["EMAIL VERIFICATION","Verify your email","Complete email verification before signing in.","verify-form"],
      forgot: ["ACCOUNT RECOVERY","Reset your password","We'll send a secure, one-time reset link if the account exists.","forgot-form"],
      reset: ["ACCOUNT RECOVERY","Choose a new password","Create a new password for your HEI account.","reset-form"]
    }[mode];
    $("auth-eyebrow").textContent = config[0]; $("auth-title").textContent = config[1]; $("auth-copy").textContent = config[2]; $(config[3]).hidden = false;
    if (mode === "login" || mode === "register") {
      $("auth-switch").hidden = false;
      $("switch-copy").textContent = mode === "login" ? "New to HEI?" : "Already have an account?";
      $("switch-button").textContent = mode === "login" ? "Create an account" : "Sign in";
    }
  }
  function busy(button, value, text) { button.disabled = value; if (value) button.dataset.label = button.textContent; button.textContent = value ? "Please wait…" : text; }
  async function api(path, options = {}, retry = true) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    const access = tokenStore.getItem("hei_access");
    if (access) headers.Authorization = "Bearer " + access;
    let response = await fetch(path, { ...options, headers });
    if (response.status === 401 && retry && tokenStore.getItem("hei_refresh") && !path.endsWith("/login")) {
      const refresh = await fetch("/api/v1/auth/refresh", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({refresh_token:tokenStore.getItem("hei_refresh")}) });
      if (refresh.ok) {
        const pair = await refresh.json(); saveSession(pair);
        headers.Authorization = "Bearer " + pair.access_token;
        response = await fetch(path, { ...options, headers });
      } else clearSession();
    }
    let body = null; try { body = await response.json(); } catch (_) {}
    if (!response.ok) { const e = new Error(body?.detail || "Request failed"); e.status = response.status; throw e; }
    return body;
  }
  function saveSession(data) { tokenStore.setItem("hei_access",data.access_token); tokenStore.setItem("hei_refresh",data.refresh_token); tokenStore.setItem("hei_user",JSON.stringify(data.user)); }
  function clearSession() { ["hei_access","hei_refresh","hei_user","hei_household"].forEach(k=>tokenStore.removeItem(k)); }
  function showDashboard(user) {
    $("auth-view").hidden = true; $("dashboard-view").hidden = false; $("top-actions").hidden = false; $("user-label").textContent = user.display_name || user.email;
    $("dashboard-title").textContent = "Good to see you" + (user.display_name ? ", " + user.display_name.split(" ")[0] : ".") + (user.display_name ? "." : "");
    loadHouseholds();
  }
  async function loadHouseholds() {
    try {
      const list = await api("/api/v1/households");
      if (list.length) {
        household = list[0]; tokenStore.setItem("hei_household",household.id);
        $("household-name").textContent = household.name; $("household-copy").textContent = "Your household workspace is ready. Your role is " + household.role + ".";
        $("household-form").hidden = true; $("household-ready").hidden = false; $("household-ready-copy").textContent = household.name + " · " + household.role;
        $("dashboard-subtitle").textContent = "Showing the workspace for " + household.name + ".";
        await loadHomeAssistant();
        await loadProperties();
      } else {
        household = null; $("household-form").hidden = false; $("household-ready").hidden = true; $("ha-panel").hidden = true;
      }
    } catch (e) { if (e.status === 401) signOut(false); else notice("We couldn't load your household workspace. Please refresh to try again.",true,"dashboard-notice"); }
  }
  function propertyNotice(message,error=false) {
    const el=$("properties-notice"); el.textContent=message; el.classList.toggle("error",error); el.hidden=false;
  }
  function node(tag,cls,text) { const el=document.createElement(tag); if(cls)el.className=cls; if(text!==undefined)el.textContent=text; return el; }
  async function loadProperties() {
    const panel=$("properties-panel"); panel.hidden=false;
    try {
      const items=await api("/api/v1/households/"+household.id+"/properties");
      $("properties-count").textContent=items.length+" PROPERT"+(items.length===1?"Y":"IES");
      $("properties-list").replaceChildren();
      $("consent-property").replaceChildren(new Option("Select a property",""));
      items.forEach(p=>{
        const opt=new Option([p.address_line_1,p.postcode].filter(Boolean).join(" · "),p.id);
        $("consent-property").add(opt);
        const card=node("article","property-card");
        const heading=node("div","property-card-heading");
        const title=node("h3",null,p.address_line_1);
        const address=node("p","muted",[p.address_line_2,p.town,p.county,p.postcode].filter(Boolean).join(", "));
        heading.append(title,node("span","tag","PROPERTY")); card.append(heading,address);
        const supplyTitle=node("h4",null,"Supply points"); card.append(supplyTitle);
        const form=node("form","supply-form");
        const fuel=node("select"); fuel.setAttribute("aria-label","Fuel type"); fuel.add(new Option("Electricity","electricity")); fuel.add(new Option("Gas","gas"));
        const identifier=node("input"); identifier.placeholder="MPAN (13/21 digits) or MPRN"; identifier.autocomplete="off"; identifier.required=true; identifier.maxLength=21; identifier.inputMode="numeric"; identifier.setAttribute("aria-label","Supply point identifier");
        const supplier=node("input"); supplier.placeholder="Supplier (optional)"; supplier.maxLength=120; supplier.setAttribute("aria-label","Supplier name");
        const submit=node("button","button button-secondary","Add supply point"); submit.type="submit";
        form.append(fuel,identifier,supplier,submit); form.addEventListener("submit",async e=>{
          e.preventDefault(); submit.disabled=true;
          try {
            await api("/api/v1/households/"+household.id+"/properties/"+p.id+"/supply-points",{method:"POST",body:JSON.stringify({fuel:fuel.value,identifier:identifier.value.trim(),supplier_name:supplier.value.trim()||null})});
            identifier.value=""; supplier.value=""; propertyNotice("Supply point saved. The identifier is encrypted and displayed in masked form."); await loadSupplyPoints(p.id,card);
          } catch(err) { propertyNotice(err.message||"Could not add this supply point.",true); } finally { submit.disabled=false; }
        });
        card.append(form);
        const points=node("div","supply-points"); points.dataset.propertyId=p.id; card.append(points);
        $("properties-list").append(card); loadSupplyPoints(p.id,card);
      });
      if(!items.length) $("properties-list").append(node("p","muted","No properties yet. Add your first property above."));
      await loadConsents();
    } catch(err) { propertyNotice(err.message||"Couldn't load properties.",true); }
  }
  async function loadSupplyPoints(propertyId,card) {
    const host=card.querySelector(".supply-points"); host.replaceChildren(node("p","hint","Loading supply points…"));
    try {
      const points=await api("/api/v1/households/"+household.id+"/properties/"+propertyId+"/supply-points");
      host.replaceChildren();
      if(!points.length) { host.append(node("p","hint","No supply points registered.")); return; }
      points.forEach(point=>{const row=node("div","supply-point-row");row.append(node("strong",null,point.fuel==="electricity"?"Electricity":"Gas"),node("span",null,point.identifier_masked),node("span","tag",point.status.toUpperCase()));host.append(row);});
    } catch(_) { host.replaceChildren(node("p","hint","Couldn't load supply points.")); }
  }
  async function loadConsents() {
    const host=$("consents-list");
    try {
      const items=await api("/api/v1/households/"+household.id+"/consents"); host.replaceChildren();
      if(!items.length) { host.append(node("p","muted","No consent records yet.")); return; }
      items.forEach(item=>{
        const row=node("article","consent-row"); const details=node("div");
        details.append(node("strong",null,item.provider+" · "+item.purpose),node("p","hint","Scopes: "+item.scopes.join(", ")));
        const actions=node("div","consent-actions"); actions.append(node("span","tag",item.status.toUpperCase()));
        if(item.status==="pending") { const grant=node("button","button button-secondary","Grant");grant.type="button";grant.addEventListener("click",async()=>{grant.disabled=true;try{await api("/api/v1/households/"+household.id+"/consents/"+item.id+"/grant",{method:"POST"});await loadConsents();propertyNotice("Consent granted.");}catch(err){propertyNotice(err.message||"Could not grant consent.",true);grant.disabled=false;}});actions.append(grant); }
        if(item.status==="granted") { const revoke=node("button","button button-quiet","Revoke");revoke.type="button";revoke.addEventListener("click",async()=>{if(!confirm("Revoke this consent?"))return;revoke.disabled=true;try{await api("/api/v1/households/"+household.id+"/consents/"+item.id+"/revoke",{method:"POST"});await loadConsents();propertyNotice("Consent revoked.");}catch(err){propertyNotice(err.message||"Could not revoke consent.",true);revoke.disabled=false;}});actions.append(revoke); }
        row.append(details,actions);host.append(row);
      });
    } catch(err) { propertyNotice(err.message||"Couldn't load consent records.",true); }
  }
  $("property-form").addEventListener("submit",async e=>{
    e.preventDefault(); const b=$("property-submit"); b.disabled=true;
    try {
      await api("/api/v1/households/"+household.id+"/properties",{method:"POST",body:JSON.stringify({address_line_1:$("property-address1").value.trim(),address_line_2:$("property-address2").value.trim()||null,town:$("property-town").value.trim(),county:$("property-county").value.trim()||null,postcode:$("property-postcode").value.trim(),country_code:"GB"})});
      $("property-form").reset(); propertyNotice("Property added."); await loadProperties();
    } catch(err) { propertyNotice(err.message||"Couldn't add property.",true); } finally { b.disabled=false; }
  });
  $("consent-form").addEventListener("submit",async e=>{
    e.preventDefault(); const b=$("consent-submit"); b.disabled=true;
    try {
      const scopes=$("consent-scopes").value.split(",").map(s=>s.trim()).filter(Boolean);
      await api("/api/v1/households/"+household.id+"/consents",{method:"POST",body:JSON.stringify({property_id:$("consent-property").value||null,provider:$("consent-provider").value.trim(),purpose:$("consent-purpose").value.trim(),scopes})});
      $("consent-form").reset(); propertyNotice("Pending consent record created. Review it below and explicitly grant it when ready."); await loadConsents();
    } catch(err) { propertyNotice(err.message||"Couldn't create consent.",true); } finally { b.disabled=false; }
  });

  async function loadHomeAssistant() {
    $("ha-panel").hidden = false;
    try {
      const status = await api("/api/v1/households/" + household.id + "/home-assistant");
      if (status.connected) {
        $("ha-url").value = status.base_url;
        $("ha-connect-form").hidden = true;
        $("ha-connected").hidden = false;
        $("ha-status").textContent = "CONNECTED";
        await refreshHomeAssistantEntities();
      } else {
        $("ha-connect-form").hidden = false;
        $("ha-connected").hidden = true;
        $("ha-status").textContent = "NOT CONNECTED";
      }
    } catch (_) { $("ha-status").textContent = "CHECK CONNECTION"; }
  }
  async function refreshHomeAssistantEntities() {
    $("ha-entities").textContent = "Loading energy sensors…";
    try {
      const data = await api("/api/v1/households/" + household.id + "/home-assistant/entities");
      $("ha-summary").textContent = data.entities.length + " energy-related sensors discovered. Choose the readings to use in a later setup step.";
      $("ha-entities").replaceChildren();
      data.entities.forEach(entity => {
        const row = document.createElement("div"); row.className = "ha-entity";
        const left = document.createElement("div"); const name = document.createElement("strong"); name.textContent = entity.name;
        const id = document.createElement("small"); id.textContent = entity.entity_id; left.append(name,id);
        const value = document.createElement("span"); value.textContent = entity.state + (entity.unit ? " " + entity.unit : "");
        row.append(left,value); $("ha-entities").append(row);
      });
    } catch (_) { $("ha-entities").textContent = "Couldn't retrieve sensors. Try refreshing."; }
  }
  $("ha-connect-form").addEventListener("submit", async e => {
    e.preventDefault();
    const button = $("ha-connect-button"); busy(button,true,"Connect Home Assistant →");
    const token = $("ha-token").value;
    try {
      const result = await api("/api/v1/households/" + household.id + "/home-assistant", {
        method:"POST", body:JSON.stringify({base_url:$("ha-url").value.trim(),token})
      }, false);
      $("ha-token").value = "";
      $("ha-connect-form").hidden = true; $("ha-connected").hidden = false;
      $("ha-status").textContent = "CONNECTED";
      $("ha-summary").textContent = result.entity_count + " energy-related sensors discovered.";
      $("ha-entities").replaceChildren();
      result.entities.forEach(entity => {
        const row=document.createElement("div");row.className="ha-entity";
        const left=document.createElement("div");const name=document.createElement("strong");name.textContent=entity.name;
        const id=document.createElement("small");id.textContent=entity.entity_id;left.append(name,id);
        const value=document.createElement("span");value.textContent=entity.state+(entity.unit?" "+entity.unit:"");row.append(left,value);$("ha-entities").append(row);
      });
    } catch(err) {
      $("ha-notice").textContent = err.message || "Home Assistant connection failed.";
      $("ha-notice").classList.add("error"); $("ha-notice").hidden = false;
    } finally { busy(button,false,"Connect Home Assistant →"); }
  });
  $("ha-refresh").addEventListener("click",refreshHomeAssistantEntities);
  $("ha-disconnect").addEventListener("click",async()=>{
    if(!confirm("Disconnect Home Assistant from this household?"))return;
    try { await api("/api/v1/households/"+household.id+"/home-assistant",{method:"DELETE"}); $("ha-connected").hidden=true;$("ha-connect-form").hidden=false;$("ha-token").value="";$("ha-status").textContent="NOT CONNECTED"; }
    catch(_) { $("ha-notice").textContent="Couldn't disconnect Home Assistant."; $("ha-notice").hidden=false; }
  });

  function signOut(callApi = true) {
    if (callApi && tokenStore.getItem("hei_access")) api("/api/v1/auth/logout",{method:"POST"}).catch(()=>{});
    clearSession(); $("dashboard-view").hidden = true; $("top-actions").hidden = true; $("auth-view").hidden = false; setMode("login");
  }

  $("switch-button").addEventListener("click",()=>setMode(currentMode==="login"?"register":"login"));
  $("forgot-link").addEventListener("click",()=>setMode("forgot"));
  $("verify-link").addEventListener("click",()=>{ $("verify-email").value=$("login-email").value.trim(); setMode("verify"); });
  $("success-action").addEventListener("click",()=>setMode("login"));
  $("logout-button").addEventListener("click",()=>signOut());
  $("login-form").addEventListener("submit",async e=>{
    e.preventDefault(); hideNotice(); const b=$("login-submit"); busy(b,true,"Sign in →");
    try { const data=await api("/api/v1/auth/login",{method:"POST",body:JSON.stringify({email:$("login-email").value.trim(),password:$("login-password").value})},false); saveSession(data); showDashboard(data.user); }
    catch(err) { notice(err.status===403?"Please verify your email before signing in. Use the verification option below.":err.status===429?"Too many attempts. Please wait before trying again.":"Email or password is incorrect.",true); }
    finally { busy(b,false,"Sign in →"); }
  });
  $("register-form").addEventListener("submit",async e=>{
    e.preventDefault(); hideNotice(); const b=$("register-submit"); busy(b,true,"Create account →");
    try { await api("/api/v1/auth/register",{method:"POST",body:JSON.stringify({email:$("register-email").value.trim(),password:$("register-password").value,display_name:$("register-name").value.trim()||null})},false); showSuccess("Check your email","Your account has been created. Open the verification link we emailed you before signing in. Email delivery must be configured by the HEI administrator."); }
    catch(err) { notice(err.status===409?"An account with this email already exists. Try signing in.":err.status===429?"Too many registration attempts. Please wait.":"We couldn't create the account. Email delivery may not be configured yet; ask the administrator to check SMTP settings.",true); }
    finally { if ($("auth-success").hidden) busy(b,false,"Create account →"); }
  });
  $("verify-form").addEventListener("submit",async e=>{
    e.preventDefault(); const b=$("verify-submit"); busy(b,true,"Resend verification →");
    try { await api("/api/v1/auth/resend-verification",{method:"POST",body:JSON.stringify({email:$("verify-email").value.trim()})},false); showSuccess("Check your inbox","If the account needs verification, a new email will arrive shortly."); }
    catch(_) { notice("We couldn't send a verification email. Please try again later.",true); }
    finally { if ($("auth-success").hidden) busy(b,false,"Resend verification →"); }
  });
  $("forgot-form").addEventListener("submit",async e=>{
    e.preventDefault(); const b=$("forgot-submit"); busy(b,true,"Send reset link →");
    try { await api("/api/v1/auth/forgot-password",{method:"POST",body:JSON.stringify({email:$("forgot-email").value.trim()})},false); showSuccess("Check your inbox","If an active verified account exists for that address, reset instructions will arrive shortly."); }
    catch(_) { notice("We couldn't process that request. Please try again later.",true); }
    finally { if ($("auth-success").hidden) busy(b,false,"Send reset link →"); }
  });
  $("reset-form").addEventListener("submit",async e=>{
    e.preventDefault(); const password=$("reset-password").value; if(password.length<12||password!==$("reset-confirm").value){notice(password.length<12?"Use at least 12 characters.":"Those passwords don't match.",true);return;}
    const b=$("reset-submit"); busy(b,true,"Update password →");
    try { await api("/api/v1/auth/reset-password",{method:"POST",body:JSON.stringify({token:new URLSearchParams(location.search).get("token"),new_password:password})},false); history.replaceState({},document.title,location.pathname); showSuccess("Password updated","Your password has changed and all existing sessions have been signed out."); }
    catch(err) { notice(err.status===400?"This reset link is invalid, expired or already used. Request a new one.":"We couldn't update your password. Please try again.",true); }
    finally { if ($("auth-success").hidden) busy(b,false,"Update password →"); }
  });
  $("household-form").addEventListener("submit",async e=>{
    e.preventDefault(); const name=$("household-input").value.trim(); if(!name)return;
    const b=$("household-form").querySelector("button"); busy(b,true,"Create household →");
    try { const h=await api("/api/v1/households",{method:"POST",body:JSON.stringify({name,country_code:"GB",timezone:"Europe/London"})}); household=h; await loadHouseholds(); }
    catch(err) { notice(err.status===401?"Your session expired. Please sign in again.":"We couldn't create your household. Please try again.",true,"dashboard-notice"); }
    finally { if(! $("household-form").hidden) busy(b,false,"Create household →"); }
  });

  async function verifyFromLink(token) {
    $("auth-view").hidden=false; $("dashboard-view").hidden=true; setMode("login");
    try { await api("/api/v1/auth/verify-email",{method:"POST",body:JSON.stringify({token})},false); history.replaceState({},document.title,"/"); showSuccess("Email verified","Your email address is confirmed. You can now sign in to HEI."); }
    catch(err) { history.replaceState({},document.title,"/?view=verify"); setMode("verify"); notice(err.status===400?"This verification link is invalid, expired or already used. Request another verification email.":"We couldn't verify that link. Please try again.",true); }
  }
  const params=new URLSearchParams(location.search); const resetToken=params.get("token"); const view=params.get("view");
  if (resetToken && location.pathname.includes("reset-password")) setMode("reset");
  else if (resetToken && location.pathname.includes("verify-email")) verifyFromLink(resetToken);
  else if (view==="register") setMode("register");
  else if (view==="verify") setMode("verify");
  else {
    const saved=tokenStore.getItem("hei_user");
    if(saved && tokenStore.getItem("hei_access")) { try { showDashboard(JSON.parse(saved)); } catch(_){clearSession();setMode("login");} }
    else setMode("login");
  }
})();