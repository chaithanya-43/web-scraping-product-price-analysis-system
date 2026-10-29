"use strict";
document.addEventListener("DOMContentLoaded",()=>{
  loadProfile();
  document.getElementById("logout-button").addEventListener("click",async()=>{await fetch("/api/auth/logout",{method:"POST"});window.location.assign("/login");});
  const sidebar=document.getElementById("app-sidebar"),scrim=document.getElementById("sidebar-scrim"),toggle=document.getElementById("sidebar-toggle");
  toggle.addEventListener("click",()=>{const open=!sidebar.classList.contains("open");sidebar.classList.toggle("open",open);scrim.classList.toggle("visible",open);toggle.setAttribute("aria-expanded",String(open));});
  scrim.addEventListener("click",()=>{sidebar.classList.remove("open");scrim.classList.remove("visible");toggle.setAttribute("aria-expanded","false");});
});
async function loadProfile(){
  try{
    const response=await fetch("/api/auth/profile");
    if(!response.ok){window.location.assign("/login");return;}
    const {user}=await response.json();
    document.getElementById("profile-name").textContent=user.name;
    document.getElementById("profile-email").textContent=user.email;
    document.getElementById("profile-created").textContent=formatDate(user.created_at);
    document.getElementById("profile-last-login").textContent=user.last_login?formatDate(user.last_login):"Not available";
    document.getElementById("sidebar-user-name").textContent=user.name;
    document.getElementById("sidebar-user-email").textContent=user.email;
    document.getElementById("user-avatar").textContent=(user.name.trim()[0]||"U").toUpperCase();
  }catch(_error){window.location.assign("/login");}
}
function formatDate(value){if(!value)return"—";const parsed=new Date(value.includes("T")?value:`${value.replace(" ","T")}Z`);return Number.isNaN(parsed.getTime())?value:parsed.toLocaleString();}
