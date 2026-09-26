import{c as o}from"./index-Sz6nW2MD.js";async function i(){const{data:t}=await o.get("/api/hotwords"),a=t.hotwords;return Array.isArray(a)?a.join(`
`):a||""}async function s(t){await o.post("/api/hotwords",{hotwords:t})}async function p(){const{data:t}=await o.get("/api/hotword-mappings"),a=t.mappings;return Array.isArray(a)?a.map(r=>`${r.from}→${r.to}`).join(`
`):a||""}async function c(t){await o.post("/api/hotword-mappings",{mappings:t})}export{p as fetchHotwordMappings,i as fetchHotwords,c as saveHotwordMappings,s as saveHotwords};
