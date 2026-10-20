/* Optional local video trim/export. Uses browser MediaRecorder when supported.
 * Leaves original file untouched. Trimming can be unavailable on some browsers.
 */
(()=>{
async function trim(video,file,start,end,smaller=false){
 if(!window.MediaRecorder||typeof video.captureStream!=='function')
   throw Error('Video trimming is not supported by this browser. You can still send the original video.');
 if(!Number.isFinite(video.duration)||end>video.duration+.05||start<0||end-start<.5||end-start>45)
   throw Error('Choose a clip from 0.5 to 45 seconds within the video.');
 const preferred=['video/webm;codecs=vp8,opus','video/webm;codecs=vp8','video/webm'];
 const codec=preferred.find(type=>MediaRecorder.isTypeSupported(type));
 if(!codec)throw Error('This browser cannot export a compatible WebM clip.');
 video.pause();
 video.currentTime=start;
 await new Promise((resolve,reject)=>{
  if(Math.abs(video.currentTime-start)<.05&&video.readyState>=2)return resolve();
  const timeout=setTimeout(()=>{video.removeEventListener('seeked',done);reject(Error('Could not seek to clip start'))},6000);
  function done(){clearTimeout(timeout);video.removeEventListener('seeked',done);resolve()}
  video.addEventListener('seeked',done);
 });
 const stream=video.captureStream();
 const recorder=new MediaRecorder(stream,{
  mimeType:codec,videoBitsPerSecond:smaller?650000:1700000,
  audioBitsPerSecond:smaller?64000:128000
 });
 const chunks=[];
 const finished=new Promise((resolve,reject)=>{
  recorder.ondataavailable=e=>{if(e.data?.size)chunks.push(e.data)};
  recorder.onerror=()=>reject(Error('Video encoding failed'));
  recorder.onstop=()=>{
   const blob=new Blob(chunks,{type:'video/webm'});
   if(!blob.size)reject(Error('Video export returned an empty file'));
   else resolve(blob);
  };
 });
 const timer=setInterval(()=>{
  if(video.currentTime>=end-.05||video.ended)finish();
 },70);
 function finish(){
  clearInterval(timer);
  video.pause();
  if(recorder.state!=='inactive')recorder.stop();
 }
 try{
  recorder.start(250);
  await video.play();
  const timeout=setTimeout(finish,Math.ceil((end-start)*1200)+4500);
  const blob=await finished.finally(()=>clearTimeout(timeout));
  return new File([blob],(file.name.replace(/\.[^/.]+$/,'')||'video')+'-clip.webm',{type:'video/webm'});
 }finally{
   clearInterval(timer);video.pause();
   try{stream.getTracks().forEach(track=>track.stop())}catch{}
 }
}
window.HuddleTrimClip={trim};
})();
