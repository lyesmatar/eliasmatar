(function(){
  var els = document.querySelectorAll('.reveal');
  if(!('IntersectionObserver' in window)){els.forEach(function(e){e.classList.add('in')});return;}
  var io = new IntersectionObserver(function(entries){
    entries.forEach(function(en){
      if(en.isIntersecting){en.target.classList.add('in');io.unobserve(en.target);}
    });
  },{rootMargin:'0px 0px -8% 0px'});
  els.forEach(function(e){io.observe(e);});
})();

/* click-to-zoom lightbox for work images */
(function(){
  var galleryImgs = document.querySelectorAll('.gallery img');
  if(!galleryImgs.length) return;
  var box = document.createElement('div');
  box.className = 'lightbox';
  box.hidden = true;
  box.setAttribute('role','dialog');
  box.setAttribute('aria-label','Enlarged image');
  box.innerHTML = '<button class="lightbox__close" aria-label="Close (Esc)">×</button><img alt="">';
  document.body.appendChild(box);
  var bimg = box.querySelector('img');
  function open(src, alt){
    bimg.src = src; bimg.alt = alt || '';
    box.hidden = false;
    document.documentElement.style.overflow = 'hidden';
  }
  function close(){
    box.hidden = true; bimg.src = '';
    document.documentElement.style.overflow = '';
  }
  galleryImgs.forEach(function(im){
    im.addEventListener('click', function(){ open(im.currentSrc || im.src, im.alt); });
  });
  box.addEventListener('click', function(e){
    if(e.target === bimg) return;   /* clicks on the image itself don't close */
    close();
  });
  document.addEventListener('keydown', function(e){
    if(e.key === 'Escape' && !box.hidden) close();
  });
})();
