// Actual upstream Studio, in separate fresh browser sessions per project.
// Browser process recycling bounds fixture memory; this does not prove a
// seamless same-tab project switch or the entire Studio product surface.
import fs from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const cfg=JSON.parse(await fs.readFile(process.argv[2],'utf8'));
const {chromium,firefox}=await import(pathToFileURL(cfg.driver));
const errors=[],requests=[],checks=[],pages=[],blocked=[];
let browser=null,context=null;
process.once('SIGTERM',async()=>{try{if(browser)await browser.close();}finally{process.exit(130);}});
async function open(){
 browser=cfg.engine==='firefox'
  ? await firefox.launch({headless:true,firefoxUserPrefs:{'dom.ipc.processCount':1,'dom.ipc.processCount.webIsolated':1}})
  : await chromium.launch({executablePath:cfg.chrome,headless:true,chromiumSandbox:true,
      args:['--disable-dev-shm-usage','--renderer-process-limit=2','--js-flags=--max-old-space-size=96']});
 context=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1280,height:800}});
 await context.route('**/*',route=>{const u=new URL(route.request().url());if(u.origin!==cfg.origin){blocked.push({origin:u.origin,path:u.pathname});return route.abort();}return route.continue();});
 await context.addCookies([{name:'__Host-dial-admin',value:cfg.token,domain:new URL(cfg.origin).hostname,path:'/',secure:true,httpOnly:true,sameSite:'Strict'}]);
 const page=await context.newPage();
 page.on('pageerror',error=>errors.push(String(error).replace(/eyJ[A-Za-z0-9_.-]+/g,'<token>')));
 page.on('response',res=>{if(res.url().includes('/api/')||res.status()>=400)requests.push({path:new URL(res.url()).pathname,status:res.status()});});
 return page;
}
async function close(){if(context)await context.close().catch(()=>{});if(browser)await browser.close().catch(()=>{});context=null;browser=null;}
let version;
try{
 for(const p of cfg.projects){
  const page=await open();version=await browser.version();
  console.log('BROWSER_CHECKPOINT '+p.name+' private-project-selector');
  await page.goto(cfg.origin+'/',{waitUntil:'domcontentloaded',timeout:15000});
  for(const x of cfg.projects)checks.push({check:p.name+'_session_selector_contains_'+x.name,pass:await page.getByRole('link',{name:x.name,exact:true}).count()===1});
  await page.getByRole('link',{name:p.name,exact:true}).click({timeout:10000});
  try{await page.getByText('admin_fixture',{exact:true}).first().waitFor({state:'visible',timeout:20000});}catch{}
  console.log('BROWSER_CHECKPOINT '+p.name+' native-editor');
  const body=await page.locator('body').innerText({timeout:5000});
  pages.push({ref:p.ref,body:body.slice(0,1800),title:await page.title()});
  checks.push({check:p.name+'_native_page_not_error',pass:!body.includes('Application error')&&!body.includes('PROJECT_NOT_AVAILABLE')});
  checks.push({check:p.name+'_rendered_table_editor_lists_fixture',pass:body.includes('admin_fixture')});
  if(body.includes('admin_fixture')){
    let clicked=false;try{await page.getByText('admin_fixture',{exact:true}).first().click({timeout:5000});clicked=true;}catch(e){errors.push('TABLE_CLICK '+String(e).split('\n')[0]);}
    checks.push({check:p.name+'_native_table_click_succeeds',pass:clicked});
    let rowVisible=false;try{await page.getByText(String(p.row_value),{exact:true}).first().waitFor({state:'visible',timeout:10000});rowVisible=true;}catch{}
    checks.push({check:p.name+'_native_table_click_displays_own_row',pass:rowVisible});
    pages.push({ref:p.ref,table_view:(await page.locator('body').innerText({timeout:5000})).slice(-2000),table_url:new URL(page.url()).pathname});
  }
  const api=await page.evaluate(async(ref)=>{
    const options={signal:AbortSignal.timeout(10000)};
    const catalogue=await fetch('/api/platform/projects',options);
    const tables=await fetch('/api/platform/pg-meta/'+ref+'/tables?included_schemas=public',options);
    const query=await fetch('/api/platform/pg-meta/'+ref+'/query',{...options,method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({query:'SELECT current_database() AS db,17 AS fixture'})});
    return {catalogue_status:catalogue.status,table_status:tables.status,tables:await tables.json(),query_status:query.status,query:await query.json()};
  },p.ref);
  checks.push({check:p.name+'_browser_cookie_catalogue',pass:api.catalogue_status===200});
  checks.push({check:p.name+'_browser_native_table_metadata',pass:api.table_status===200&&api.tables.some(x=>x.name==='admin_fixture')});
  checks.push({check:p.name+'_browser_scoped_sql_response',pass:api.query_status===200&&api.query[0].db===p.database});
  console.log('BROWSER_CHECKPOINT '+p.name+' complete');
  await close();
 }
 console.log(JSON.stringify({state:checks.every(x=>x.pass)?'PASS':'FAIL',checks,errors,requests,pages,blocked,
    browser_engine:cfg.engine,browser_version:version,fixture_network_only:true,sandbox_explicitly_disabled:false,
    chromium_sandbox_required:true,separate_browser_sessions:true,full_studio_ui_qualified:false}));
}finally{await close();}
