// FILE: static/script.js
document.addEventListener('click', (e)=>{
  // Quick visual ripple for buttons
  const btn = e.target.closest('.btn');
  if(!btn) return;
  btn.style.transform = 'translateY(0)';
  btn.classList.add('clicked');
  setTimeout(()=>btn.classList.remove('clicked'), 150);
});
