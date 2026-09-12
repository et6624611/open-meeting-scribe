const n=[255,155,35,285,5,185,55,325];function c(t){const e=typeof t=="string"?parseInt(t.replace(/\D/g,"").slice(-2))||1:t;return`oklch(60% 0.055 ${n[e%n.length]})`}export{c as g};
