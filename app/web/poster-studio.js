/* Huddle Poster Studio — offline canvas-based graphic creator.
   Generates stylized graphic posters from prompts. This is NOT photorealistic AI. */
const themes=[
  {words:/sunset|sunrise|golden|orange|beach|warm/,palette:['#ff8b65','#f8b16e','#633d86','#2b244b'],kind:'sunset'},
  {words:/mountain|trek|hiking|hill|mandi|nature|forest/,palette:['#112842','#335f78','#88b8b7','#e7dbc5'],kind:'mountain'},
  {words:/space|galaxy|cosmic|star|night|universe/,palette:['#1b1d57','#5442a6','#bc78d4','#f5c7a2'],kind:'cosmic'},
  {words:/ocean|sea|water|blue|wave/,palette:['#072e4b','#12798d','#45b9be','#dcf8f6'],kind:'ocean'},
  {words:/love|flower|pink|soft|romantic|pastel/,palette:['#512c68','#b477b4','#f2acc1','#ffe5d9'],kind:'flower'},
  {words:/study|college|university|work|business|hackathon|tech|future/,palette:['#142446','#4163af','#8c70d6','#8de1d1'],kind:'abstract'}
];
function hashText(text){let n=2166136261;for(const c of text){n=Math.imul(n^c.charCodeAt(0),16777619);}return n>>>0;}
function getTheme(prompt){return themes.find(item=>item.words.test(prompt.toLowerCase()))||themes[5];}
function fitText(ctx,text,x,y,width,size,rows,color){
  const words=text.trim().split(/\s+/).filter(Boolean);if(!words.length)return y;
  let lines=[],line='';ctx.font='800 '+size+'px Manrope, system-ui, sans-serif';
  for(const word of words){const candidate=line?line+' '+word:word;
    if(ctx.measureText(candidate).width>width&&line){lines.push(line);line=word;}else line=candidate;
  }
  if(line)lines.push(line);
  if(lines.length>rows){lines=lines.slice(0,rows);let last=lines[rows-1];while(last.length>1&&ctx.measureText(last+'…').width>width)last=last.slice(0,-1);lines[rows-1]=last+'…';}
  ctx.fillStyle=color;ctx.textAlign='center';ctx.textBaseline='middle';
  for(const text of lines){ctx.fillText(text,x,y);y+=size*1.12;}return y;
}
function poly(ctx,pts,color){ctx.fillStyle=color;ctx.beginPath();ctx.moveTo(pts[0][0],pts[0][1]);for(const [x,y] of pts.slice(1))ctx.lineTo(x,y);ctx.closePath();ctx.fill();}
function circle(ctx,x,y,r,color){ctx.fillStyle=color;ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fill();}
function drawBackground(ctx,theme,seed){
  const S=1080,colors=theme.palette;
  const bg=ctx.createLinearGradient(0,0,S,S);bg.addColorStop(0,colors[0]);bg.addColorStop(.56,colors[1]);bg.addColorStop(1,colors[2]);ctx.fillStyle=bg;ctx.fillRect(0,0,S,S);
  const rng=(()=>{let n=seed||1;return()=>{n=(Math.imul(n,1664525)+1013904223)>>>0;return n/4294967296}})();
  if(theme.kind==='sunset'||theme.kind==='mountain'){
    circle(ctx,765,365,176,theme.kind==='sunset'?'#ffdfab':'#fbefd7');
    poly(ctx,[[0,760],[210,440],[430,690],[700,290],[1080,740],[1080,1080],[0,1080]],colors[2]);
    poly(ctx,[[0,940],[180,700],[370,940],[620,550],[890,870],[1080,660],[1080,1080],[0,1080]],colors[3]);
    if(theme.kind==='mountain')poly(ctx,[[615,630],[700,290],[772,492],[738,465],[698,420],[665,468]],'#e6ede9');
  } else if(theme.kind==='ocean'){
    circle(ctx,810,300,180,'#dcf8f6');
    for(let j=0;j<5;j++){
      ctx.fillStyle=j%2?colors[0]:colors[2];ctx.beginPath();ctx.moveTo(0,650+j*110);
      for(let x=0;x<=S;x+=12)ctx.lineTo(x,650+j*110+Math.sin(x/86+j*1.2)*28);ctx.lineTo(S,S);ctx.lineTo(0,S);ctx.fill();
    }
  } else if(theme.kind==='cosmic'){
    for(let i=0;i<125;i++)circle(ctx,rng()*S,rng()*S,rng()*2.2+1,'#ffffff'+(rng()>.5?'be':'75'));
    circle(ctx,795,340,200,colors[2]);circle(ctx,744,285,189,colors[0]);
    ctx.strokeStyle='#f8d7f2';ctx.lineWidth=3;ctx.beginPath();ctx.ellipse(795,340,250,75,-.34,0,Math.PI*2);ctx.stroke();
  } else if(theme.kind==='flower'){
    for(let i=0;i<8;i++){
      const a=i*Math.PI/4;circle(ctx,730+Math.cos(a)*132,385+Math.sin(a)*132,115,colors[2]);
    }circle(ctx,730,385,106,'#ffe1b6');
    for(let i=0;i<25;i++){circle(ctx,rng()*S,rng()*S,rng()*7+3,'#ffffff36');}
  } else {
    for(let i=0;i<9;i++){const x=rng()*S,y=rng()*S,r=rng()*180+70;
      circle(ctx,x,y,r,i%2?colors[2]+'66':colors[3]+'66');}
    ctx.strokeStyle='#ffffff46';ctx.lineWidth=2;
    for(let i=0;i<12;i++){ctx.beginPath();ctx.arc(740,480,120+i*52,-.9,1.2);ctx.stroke();}
  }
  const shade=ctx.createLinearGradient(0,450,0,1080);shade.addColorStop(0,'#11163800');shade.addColorStop(1,'#10132eaf');
  ctx.fillStyle=shade;ctx.fillRect(0,450,S,630);
}
function getTitle(prompt){
  const cleaned=prompt.replace(/^(?:please |can you |make |create |design |generate |draw |give me )+/gi,'').replace(/(?:a |an )?(?:poster|wallpaper|image|graphic|card|banner|background)\s*(?:of|for|about|with|that says|saying|featuring)?\s*/gi,'').replace(/(?:in|with)\s+(?:a\s+)?(?:beautiful|aesthetic|minimal|pastel|realistic|4k|cute|high quality|modern|purple|blue|pink|green)\s*(?:style|colors?)?/gi,'').replace(/[.!?]+$/,'').trim();
  return (cleaned||'MAKE IT HAPPEN').slice(0,110);
}
export async function createPoster(prompt){
  if(typeof document==='undefined')throw Error('Poster Studio needs an image-capable browser.');
  const title=getTitle(prompt);const theme=getTheme(prompt);
  const canvas=document.createElement('canvas');canvas.width=1080;canvas.height=1080;
  const ctx=canvas.getContext('2d');if(!ctx)throw Error('Your browser does not support drawing images.');
  drawBackground(ctx,theme,hashText(prompt));
  ctx.fillStyle='#ffffffe8';ctx.textAlign='left';ctx.font='800 24px Manrope, system-ui, sans-serif';ctx.fillText('H U D D L E  /  S T U D I O',65,86);
  ctx.fillStyle='#ffffff';ctx.fillRect(65,112,80,6);
  const y=fitText(ctx,title.toUpperCase(),540,790,935,title.length>55?48:title.length>29?58:76,3,'#ffffff');
  ctx.font='600 22px Manrope, system-ui, sans-serif';ctx.fillStyle='#f5f3ffde';ctx.textAlign='center';
  ctx.fillText('MADE TO SHARE  •  CREATED IN HUDDLE',540,Math.min(1000,y+34));
  return {dataUrl:canvas.toDataURL('image/png'),title,kind:theme.kind,description:'Graphic poster created in your browser. Not a photorealistic AI image.'};
}