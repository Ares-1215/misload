// 自動判責爬蟲（2026-08-17）——使用者說「自動判責」時由 Claude 執行，非網站功能
// 流程：
//   1. SQL 撈 misload_details 中 resp_station in (彰化,彰轉,彰化低溫)、resp_unit 空白的 (send_date, tracking_no)
//   2. 瀏覽器面板開 https://cagweb.hct.com.tw:8080/apex.aspx?apex=CAGWEB.A_PIKAM010 請使用者登入
//   3. 把去重後的貨號清單填入下方 NOS，整段用 javascript_tool 注入（fetch/XHR 被擋，用隱藏 iframe 逐筆導航）
//   4. 輪詢 window.__au.done/running，完成後取 JSON.stringify(window.__au.results)
//   5. 結果組成 {passcode:"<管理員帳:密>",action:"auto_units",rows:[{send_date,tracking_no,unit}]}
//      以 PowerShell Invoke-RestMethod (Tls12, UTF8 bytes) POST 到 Edge Function misload
//      auto_units 只更新 resp_unit IS NULL 的列，人工/回傳檔已填的不會被覆蓋
//
// 判定規則（依序，2026-08-17 使用者指定）：
//   1. 追蹤紀錄任一列出現「黃弘儒」，或 商品區分1/2 含 冷凍/冷藏 → 冷鏈
//   2. 否則有「作業=發送＋站所=彰化＋運輸方式含籠車」 → 籠車
//   3. 否則 頁首「到著站」=彰化 且追蹤有「到著＠彰化」紀錄 → 比較時間順序（2026-08-17 精修）：
//      彰化到著時間 早於 誤站(註區站)首次出現 → 到轉（到著班點收後才誤流，如 4522172911：02:33 彰化到著→05:34 烏日）
//      誤站出現 早於 彰化到著 → 發送階段就誤裝，落到規則 4 用發送時間判（如 3448836425：01:36 到著烏日→彰轉 16:06 發送→發轉）
//      找不到誤站事件無法比較時 → 預設 到轉
//   4. 否則取最早的彰化(含彰轉/彰化低溫)發送事件時間：01:00~12:59 → 到轉；13:00~00:59 → 發轉
//   5. 無彰化發送紀錄 → 不填，列出給使用者人工確認
//   ※ NOS 每筆要帶 DB 的註區站：[{no:"十碼貨號", wrong:"註區站"}, ...]

(function(){
  const NOS = [/* 這裡填去重後的 {no:"十碼貨號", wrong:"註區站"} 物件陣列 */];
  const CHQ = ["彰化","彰轉","彰化低溫"];
  window.__au = {done:0,total:NOS.length,results:[],running:true,err:null};
  const fr = document.createElement("iframe");
  fr.style.cssText = "position:fixed;width:2px;height:2px;left:-9999px;top:0;border:0";
  (document.body||document.documentElement).appendChild(fr);
  const loadDoc = (url) => new Promise((res)=>{
    let fin=false;
    const t=setTimeout(()=>{ if(!fin){fin=true;res(null);} },20000);
    fr.onload=()=>{ setTimeout(()=>{ if(!fin){fin=true;clearTimeout(t);try{res(fr.contentDocument);}catch(e){res(null);}} },600); };
    fr.src=url;
  });
  const judge = (doc,no,wrong)=>{
    if(!doc||!doc.body) return {no,unit:null,why:"頁面載入失敗"};
    const txt = doc.body.innerText||"";
    if(!txt.includes("作業時間")) return {no,unit:null,why:"查無追蹤資料"};
    let cold=false, coldVal="", destSt="";
    const tds=[...doc.querySelectorAll("td,th")];
    for(let i=0;i<tds.length-1;i++){
      const a=(tds[i].innerText||"").trim();
      const v=(tds[i+1].innerText||"").trim();
      if(a==="商品區分1"||a==="商品區分2"){ if(/冷凍|冷藏/.test(v)){ cold=true; coldVal=v; } }
      if(a==="到著站" && !destSt) destSt=v;
    }
    let ops=[];
    for(const t of doc.querySelectorAll("table")){
      const first=t.querySelector("tr");
      if(!first) continue;
      const heads=[...first.querySelectorAll("td,th")].map(c=>(c.innerText||"").trim());
      if(heads.includes("作業時間")&&heads.includes("站所")){
        const iT=heads.indexOf("作業時間"),iOp=heads.indexOf("作業"),iSt=heads.indexOf("站所");
        const iWay=heads.findIndex(h=>h.includes("輸方式"));
        ops=[...t.querySelectorAll("tr")].slice(1).map(tr=>{
          const c=[...tr.querySelectorAll("td")].map(x=>(x.innerText||"").trim());
          return {time:c[iT]||"",op:c[iOp]||"",st:c[iSt]||"",way:iWay>=0?(c[iWay]||""):"",raw:c.join("|")};
        }).filter(r=>/\d{1,2}:\d{2}/.test(r.time));
        if(ops.length) break;
      }
    }
    const hung = ops.some(r=>r.raw.includes("黃弘儒"));
    if(hung||cold) return {no,unit:"冷鏈",why:hung?(cold?"黃弘儒＋"+coldVal:"出現黃弘儒"):"商品區分"+coldVal};
    const cage = ops.find(r=>r.op==="發送"&&r.st==="彰化"&&r.way.includes("籠車"));
    if(cage) return {no,unit:"籠車",why:"彰化發送籠車貨件 "+cage.time};
    const arr = ops.filter(r=>r.op==="到著"&&r.st==="彰化").sort((a,b)=>a.time<b.time?-1:1);
    if(destSt==="彰化" && arr.length){
      const wrongEvts = wrong ? ops.filter(r=>r.st===wrong).sort((a,b)=>a.time<b.time?-1:1) : [];
      if(!wrongEvts.length) return {no,unit:"到轉",why:"到著站彰化＋彰化到著 "+arr[0].time+"（無"+(wrong||"註區站")+"事件可比對，預設到轉）"};
      if(arr[0].time < wrongEvts[0].time) return {no,unit:"到轉",why:"彰化到著 "+arr[0].time+" 後才誤流"+wrong+" "+wrongEvts[0].time};
      // 誤站早於彰化到著 → 發送階段就誤裝，落到發送時間規則
    }
    const sends = ops.filter(r=>r.op==="發送"&&CHQ.includes(r.st)).sort((a,b)=>a.time<b.time?-1:1);
    if(!sends.length) return {no,unit:null,why:"無彰化發送紀錄"};
    const m=sends[0].time.match(/(\d{1,2}):\d{2}\s*$/);
    if(!m) return {no,unit:null,why:"發送時間無法解析:"+sends[0].time};
    const h=parseInt(m[1],10);
    const unit=(h>=1&&h<13)?"到轉":"發轉";
    return {no,unit,why:"彰化發送 "+sends[0].time+(unit==="到轉"?"（凌晨班→到轉）":"（傍晚班→發轉）")};
  };
  (async()=>{
    try{
      for(const item of NOS){
        const doc=await loadDoc("https://cagweb.hct.com.tw:8080/CAGWEB/C_PIKAM020.aspx?pACT=C_PIKAM010&pINVOICE_NO="+item.no+"&pADDITION_NO=000&pHCd=&pHDay=");
        window.__au.results.push(judge(doc,item.no,item.wrong));
        window.__au.done++;
      }
    }catch(e){ window.__au.err=String(e); }
    window.__au.running=false;
  })();
  return "started "+NOS.length+" nos";
})()
