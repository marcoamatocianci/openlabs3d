/* Runs before the stylesheet to avoid a wrong-theme flash. */
function applyTheme(choice){const dark=choice==='dark'||choice==='system'&&matchMedia('(prefers-color-scheme: dark)').matches;document.documentElement.dataset.theme=dark?'dark':'light';try{localStorage.setItem('ol3d-appearance',choice)}catch(e){}}
try{applyTheme(localStorage.getItem('ol3d-appearance')||'system')}catch(e){applyTheme('system')}
matchMedia('(prefers-color-scheme: dark)').addEventListener('change',()=>{if((localStorage.getItem('ol3d-appearance')||'system')==='system')applyTheme('system')});
