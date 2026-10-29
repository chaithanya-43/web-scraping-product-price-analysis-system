"use strict";
let allHistory=[];
document.addEventListener("DOMContentLoaded",()=>{
  loadIdentity();loadHistory();
  document.getElementById("history-search").addEventListener("input",renderHistory);
  document.getElementById("logout-button").addEventListener("click",async()=>{await fetch("/api/auth/logout",{method:"POST"});window.location.assign("/login");});
  const sidebar=document.getElementById("app-sidebar"),scrim=document.getElementById("sidebar-scrim"),toggle=document.getElementById("sidebar-toggle");
  toggle.addEventListener("click",()=>{const open=!sidebar.classList.contains("open");sidebar.classList.toggle("open",open);scrim.classList.toggle("visible",open);toggle.setAttribute("aria-expanded",String(open));});
  scrim.addEventListener("click",()=>{sidebar.classList.remove("open");scrim.classList.remove("visible");toggle.setAttribute("aria-expanded","false");});
});
async function loadIdentity(){try{const response=await fetch("/api/auth/profile");if(!response.ok){window.location.assign("/login");return;}const {user}=await response.json();document.getElementById("sidebar-user-name").textContent=user.name;document.getElementById("sidebar-user-email").textContent=user.email;document.getElementById("user-avatar").textContent=(user.name.trim()[0]||"U").toUpperCase();}catch(_error){window.location.assign("/login");}}
async function loadHistory(){
  const status=document.getElementById("history-status");
  try{const response=await fetch("/api/history");if(!response.ok){if(response.status===401)window.location.assign("/login");throw new Error("Analysis history could not be loaded.");}const data=await response.json();allHistory=data.history||[];renderHistory();}
  catch(error){status.textContent=error.message;status.classList.remove("hidden");status.classList.add("error");}
}
function renderHistory(){
  const query=document.getElementById("history-search").value.trim().toLowerCase();
  const rows=allHistory.filter(item=>String(item.source_name||item.source_url).toLowerCase().includes(query));
  document.getElementById("history-count").textContent=String(allHistory.length);
  document.getElementById("history-empty").classList.toggle("hidden",rows.length>0);
  document.getElementById("history-table").innerHTML=rows.map(item=>{
    const average=item.average_price===null?"—":`${symbol(item.currency)}${Number(item.average_price).toFixed(2)}`;
    const destination=`/dashboard?analysis=${encodeURIComponent(item.id)}`;
    return `<tr><td><b>${escapeHtml(item.source_name||item.source_url)}</b><small class="history-url">${escapeHtml(item.source_url)}</small></td><td>${Number(item.products_found)||0}</td><td class="price-cell">${average}</td><td>${escapeHtml(formatDate(item.analyzed_at))}</td><td><a class="history-link" href="${destination}">View analysis ↗</a></td></tr>`;
  }).join("");
}
function symbol(currency){return({GBP:"£",USD:"$",EUR:"€",INR:"₹"})[currency]||(currency?`${currency} `:"");}
function escapeHtml(value){const span=document.createElement("span");span.textContent=value??"";return span.innerHTML;}
function formatDate(value){if(!value)return"—";const date=new Date(value.includes("T")?value:`${value.replace(" ","T")}Z`);return Number.isNaN(date.getTime())?value:date.toLocaleString();}
