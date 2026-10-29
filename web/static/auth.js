"use strict";
document.addEventListener("DOMContentLoaded",()=>{
  document.querySelectorAll("[data-toggle-password]").forEach(button=>button.addEventListener("click",()=>{const input=document.getElementById(button.dataset.togglePassword);const show=input.type==="password";input.type=show?"text":"password";button.textContent=show?"Hide":"Show";input.focus();}));
  const login=document.getElementById("login-form");if(login)login.addEventListener("submit",loginSubmit);
  const signup=document.getElementById("signup-form");if(signup)signup.addEventListener("submit",signupSubmit);
  const password=document.getElementById("password");if(password&&document.getElementById("strength-bar"))password.addEventListener("input",()=>updateStrength(password.value,"strength-bar","strength-label"));
  const resetPassword=document.getElementById("new-password");if(resetPassword)resetPassword.addEventListener("input",()=>updateStrength(resetPassword.value,"reset-strength-bar","reset-strength-label"));
  if(document.getElementById("forgot-request-form"))initRecovery();
});

async function loginSubmit(event){
  event.preventDefault();const form=event.currentTarget;setBusy(form,true,"Signing in…");
  try{const result=await postJson("/api/auth/login",{email:document.getElementById("email").value.trim(),password:document.getElementById("password").value});if(!result.response.ok)throw new Error(result.data.error||"Sign in failed.");showMessage("Signed in. Opening your workspace…","success");window.setTimeout(()=>window.location.assign("/dashboard"),350);}
  catch(error){showMessage(error.message,"error");}finally{setBusy(form,false,"Sign in");}
}

async function signupSubmit(event){
  event.preventDefault();const form=event.currentTarget;setBusy(form,true,"Creating account…");
  try{const result=await postJson("/api/auth/signup",{name:document.getElementById("name").value.trim(),email:document.getElementById("email").value.trim(),password:document.getElementById("password").value});if(!result.response.ok)throw new Error(result.data.error||"Account creation failed.");showMessage("Account created. You can sign in now.","success");window.setTimeout(()=>window.location.assign("/login"),750);}
  catch(error){showMessage(error.message,"error");}finally{setBusy(form,false,"Create account");}
}

function initRecovery(){
  let resetToken=null,email="",expiryTimer=null,resendTimer=null;
  const requestForm=document.getElementById("forgot-request-form"),otpForm=document.getElementById("verify-otp-form"),resetForm=document.getElementById("reset-password-form");
  requestForm.addEventListener("submit",async event=>{event.preventDefault();email=document.getElementById("recovery-email").value.trim();await requestCode(false);});
  otpForm.addEventListener("submit",async event=>{
    event.preventDefault();const form=event.currentTarget;setBusy(form,true,"Verifying…");
    try{const result=await postJson("/api/auth/verify-otp",{email,otp:document.getElementById("otp").value.trim()});if(!result.response.ok)throw new Error(result.data.error||"The code is invalid or expired.");resetToken=result.data.reset_token;showStep("recovery-password-step",2);clearMessage();document.getElementById("new-password").focus();}
    catch(error){showMessage(error.message,"error");document.getElementById("otp").select();}finally{setBusy(form,false,"Verify code");}
  });
  document.getElementById("resend-otp").addEventListener("click",()=>requestCode(true));
  resetForm.addEventListener("submit",async event=>{
    event.preventDefault();const form=event.currentTarget;const password=document.getElementById("new-password").value,confirmation=document.getElementById("confirm-password").value;
    if(password!==confirmation){showMessage("The passwords do not match.","error");return;}
    setBusy(form,true,"Updating password…");
    try{const result=await postJson("/api/auth/reset-password",{reset_token:resetToken,new_password:password,confirm_password:confirmation});if(!result.response.ok)throw new Error(result.data.error||"Password could not be updated.");resetToken=null;if(expiryTimer)clearInterval(expiryTimer);showStep("recovery-success-step",3);showMessage("Password updated successfully.","success");}
    catch(error){showMessage(error.message,"error");}finally{setBusy(form,false,"Update password");}
  });

  async function requestCode(resend){
    const form=resend?otpForm:requestForm;setBusy(form,true,resend?"Sending again…":"Sending code…");
    try{const result=await postJson("/api/auth/forgot-password",{email});if(!result.response.ok)throw new Error(result.data.error||"The request could not be completed.");
      showStep("recovery-otp-step",1);document.getElementById("otp").value="";document.getElementById("otp").focus();
      showMessage("If this email matches an account, a code has been sent. Check your inbox and spam folder.");
      if(expiryTimer)clearInterval(expiryTimer);expiryTimer=startCountdown(600,document.getElementById("otp-expiry"),value=>{if(value===0)showMessage("This code has expired. Request a new code to continue.","error");});
      if(resendTimer)clearInterval(resendTimer);let remaining=60;const resendButton=document.getElementById("resend-otp"),label=document.getElementById("resend-countdown");resendButton.disabled=true;label.textContent=`Resend available in ${remaining} seconds`;
      resendTimer=window.setInterval(()=>{remaining--;label.textContent=remaining>0?`Resend available in ${remaining} seconds`:"You can request a new code.";resendButton.disabled=remaining>0;if(remaining<=0)clearInterval(resendTimer);},1000);
    }catch(error){showMessage(error.message,"error");}finally{setBusy(form,false,resend?"Verify code":"Send verification code");}
  }

  function showStep(id,index){document.querySelectorAll(".recovery-step").forEach(step=>step.classList.add("hidden"));document.getElementById(id).classList.remove("hidden");document.querySelectorAll("#recovery-progress span").forEach((bar,barIndex)=>bar.classList.toggle("done",barIndex<=index));}
}

function startCountdown(seconds,element,onTick){let remaining=seconds;const render=()=>{const minutes=Math.floor(remaining/60),secs=remaining%60;element.textContent=`${minutes}:${String(secs).padStart(2,"0")}`;if(onTick)onTick(remaining);};render();const timer=window.setInterval(()=>{remaining=Math.max(0,remaining-1);render();if(remaining===0)window.clearInterval(timer);},1000);return timer;}
async function postJson(url,data){const response=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});let payload={};try{payload=await response.json();}catch(_error){}return{response,data:payload};}
function showMessage(text,variant=""){const element=document.getElementById("auth-status");element.textContent=text;element.className=`auth-message${variant?` ${variant}`:""}`;}
function clearMessage(){const element=document.getElementById("auth-status");element.textContent="";element.classList.add("hidden");}
function setBusy(form,busy,label){const button=form.querySelector("button[type=submit]");if(!button)return;button.disabled=busy;const text=button.querySelector("span:first-child");if(text)text.textContent=label;else button.textContent=label;}
function updateStrength(value,barId,labelId){const bar=document.getElementById(barId),label=document.getElementById(labelId);let score=0;if(value.length>=8)score++;if(value.length>=12)score++;if(/[A-Z]/.test(value)&&/[a-z]/.test(value))score++;if(/\d/.test(value))score++;if(/[^A-Za-z0-9]/.test(value))score++;const width=[0,22,43,65,83,100][score];bar.style.width=`${width}%`;bar.style.background=score<2?"#ef4444":score<4?"#f59e0b":"#22c55e";label.textContent=value.length===0?"Use a longer password with mixed character types.":score<2?"Weak · add length and variety.":score<4?"Fair · add another character type.":"Strong password.";}
