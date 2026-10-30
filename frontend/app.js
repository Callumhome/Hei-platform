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
      } else {
        household = null; $("household-form").hidden = false; $("household-ready").hidden = true; $("ha-panel").hidden = true;
      }
    } catch (e) { if (e.status === 401) signOut(false); else notice("We couldn't load your household workspace. Please refresh to try again.",true,"dashboard-notice"); }
  }
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