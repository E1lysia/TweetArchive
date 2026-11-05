// Pure local script checks. This creates no browser and makes no network calls.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const path=require('path'),root=process.argv[2];
class Element {
  constructor(){this.children=[];this.value='';this.textContent='';this.listeners={};}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=items;}
  addEventListener(event,fn){this.listeners[event]=fn;}
}
const ids=['search','account','view','status','month','stats','results','empty','page','prev','next'];
const elements=Object.fromEntries(ids.map(id=>[id,new Element()]));elements.status.value='archived';
elements.view.value='bilingual';
const context={document:{getElementById:id=>elements[id],createElement:()=>new Element()},window:{scrollTo:()=>{}},console};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(root,'_推文归档/data.js'),'utf8'),context);
const html=fs.readFileSync(path.join(root,'推文归档.html'),'utf8');
const code=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]).join('\n');
new vm.Script(code);vm.runInContext(code,context);
assert(!html.includes('<script src='),'离线页面应内嵌数据，无需加载外部脚本');
assert(elements.results.children.length>0,'应显示原文卡片');
assert(elements.results.children.length<=16,'应分页');
assert(context.window.TWEET_ARCHIVE.every(d=>d.status!=='excluded'),'不应显示已排除推文');
assert(context.window.TWEET_ARCHIVE.every(d=>d.status!=='archived'||['original','quote','retweet','reference'].includes(d.post_type)),'已核对内容应有明确类型');
const record=context.window.TWEET_ARCHIVE.find(d=>d.status==='archived');
elements.search.value=record.tweet_id;elements.search.listeners.input();
assert.equal(elements.results.children.length,1,'ID 搜索应唯一匹配');
const translatedRecord=context.window.TWEET_ARCHIVE.find(d=>d.translation_zh);
if(translatedRecord){
  elements.search.value=translatedRecord.tweet_id;elements.search.listeners.input();
  const labels=()=>elements.results.children[0].children.filter(e=>e.className?.startsWith('text-block')).map(e=>e.children[0].textContent);
  assert(labels().includes('原文')&&labels().includes('中文译文'),'双语模式应显示两种文字');
  elements.view.value='zh';elements.view.listeners.input();assert.deepEqual(labels(),['中文译文']);
  elements.view.value='original';elements.view.listeners.input();assert.deepEqual(labels(),['原文']);
  elements.view.value='bilingual';
  elements.search.value=translatedRecord.translation_zh;elements.search.listeners.input();
  assert(elements.results.children.length>0,'应能搜索中文译文');
}
elements.search.value='__no_matching_record__';elements.search.listeners.input();
assert.equal(elements.results.children.length,0);assert.equal(elements.empty.hidden,false);
elements.search.value='';elements.status.value='pending';elements.status.listeners.input();
assert.equal(elements.results.children.length,Math.min(16,context.window.TWEET_ARCHIVE.filter(d=>d.status==='pending').length));
let images=0,videos=0;for(const d of context.window.TWEET_ARCHIVE){for(const image of d.images){assert(fs.existsSync(path.join(root,image)),image);images++;}for(const video of d.videos||[]){assert(fs.existsSync(path.join(root,video)),video);videos++;}}
assert(videos>0,'现有本地视频应出现在离线归档中');
console.log(JSON.stringify({records:context.window.TWEET_ARCHIVE.length,linkedImages:images,linkedVideos:videos,checks:'分页、搜索、内容类型、状态筛选和本地媒体路径通过'}));
