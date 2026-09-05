/**
 * PaySplit Presentation Engine
 * Pure Vanilla JavaScript for slide transitions & simple 2-button navigation.
 */

document.addEventListener('DOMContentLoaded', () => {
  const slides = document.querySelectorAll('.slide');
  const totalSlides = slides.length;
  let currentIndex = 0;
  const hash = window.location.hash;
  if (hash) {
    const targetSlide = document.querySelector(hash);
    if (targetSlide) {
      const targetIndex = Array.from(slides).indexOf(targetSlide);
      if (targetIndex !== -1) currentIndex = targetIndex;
    }
  }

  // Navigation Buttons
  const btnPrev = document.getElementById('btnPrev');
  const btnNext = document.getElementById('btnNext');

  /**
   * Update Slide View and Navigation State
   */
  function updateSlide(newIndex) {
    if (newIndex < 0 || newIndex >= totalSlides) return;

    // Update active slide class
    slides.forEach((slide, idx) => {
      if (idx === newIndex) {
        slide.classList.add('active');
      } else {
        slide.classList.remove('active');
      }
    });

    currentIndex = newIndex;

    // Update URL hash without scrolling
    const activeSlide = slides[currentIndex];
    if (activeSlide && activeSlide.id) {
      history.replaceState(null, '', `#${activeSlide.id}`);
    }

    // Update 2-button disabled state
    if (btnPrev) {
      btnPrev.disabled = (currentIndex === 0);
    }
    if (btnNext) {
      btnNext.disabled = (currentIndex === totalSlides - 1);
    }

    // Update slide page number counter (e.g. 01 / 04)
    const slideCounter = document.getElementById('slideCounter');
    if (slideCounter) {
      const current = String(currentIndex + 1).padStart(2, '0');
      const total = String(totalSlides).padStart(2, '0');
      slideCounter.innerHTML = `<span class="current-slide">${current}</span><span class="slide-sep">/</span><span class="total-slides">${total}</span>`;
    }
  }

  function nextSlide() {
    if (currentIndex < totalSlides - 1) {
      updateSlide(currentIndex + 1);
    }
  }

  function prevSlide() {
    if (currentIndex > 0) {
      updateSlide(currentIndex - 1);
    }
  }

  // Click Listeners
  if (btnNext) btnNext.addEventListener('click', nextSlide);
  if (btnPrev) btnPrev.addEventListener('click', prevSlide);

  // Keyboard Navigation (Arrow Keys & Space)
  document.addEventListener('keydown', (e) => {
    switch (e.key) {
      case 'ArrowRight':
      case 'PageDown':
      case ' ': // Spacebar
        e.preventDefault();
        nextSlide();
        break;

      case 'ArrowLeft':
      case 'PageUp':
        e.preventDefault();
        prevSlide();
        break;

      case 'Home':
        e.preventDefault();
        updateSlide(0);
        break;

      case 'End':
        e.preventDefault();
        updateSlide(totalSlides - 1);
        break;
    }
  });

  // Slide 2: Nút mũi tên hiển thị 3 ô giải pháp
  const btnToggleAll = document.getElementById('btnToggleAllSolution');
  const slide2 = document.getElementById('slide-2');

  if (btnToggleAll && slide2) {
    btnToggleAll.addEventListener('click', (e) => {
      e.stopPropagation();
      slide2.classList.toggle('show-solutions');
      const isSolved = slide2.classList.contains('show-solutions');

      btnToggleAll.setAttribute('title', isSolved ? 'Thu gọn giải pháp' : 'Xem giải pháp PaySplit');
      btnToggleAll.setAttribute('aria-label', isSolved ? 'Thu gọn giải pháp' : 'Xem giải pháp PaySplit');
    });
  }

  // Dynamic Responsive Scaling for SVG + HTML Diagram Boards (Slide 3 & Slide 4)
  function scaleDiagramBoards() {
    // Scale Slide 3
    const contextWrapper = document.querySelector('.system-context-wrapper');
    const contextBoard = document.querySelector('.system-context-board');
    if (contextWrapper && contextBoard) {
      const baseW = 1440;
      const baseH = 580;
      const availW = contextWrapper.clientWidth;
      if (availW > 0) {
        const scale = Math.min(1, availW / baseW);
        contextBoard.style.transform = `scale(${scale})`;
        contextWrapper.style.height = `${baseH * scale}px`;
      }
    }

    // Scale Slide 4
    const archWrapper = document.querySelector('.internal-arch-wrapper');
    const archBoard = document.querySelector('.internal-arch-board');
    if (archWrapper && archBoard) {
      const baseW = 1600;
      const baseH = 620;
      const availW = archWrapper.clientWidth;
      if (availW > 0) {
        const scale = Math.min(1, availW / baseW);
        archBoard.style.transform = `scale(${scale})`;
        archWrapper.style.height = `${baseH * scale}px`;
      }
    }
  }

  window.addEventListener('resize', scaleDiagramBoards);

  // Hook into slide change
  const originalUpdateSlide = updateSlide;
  updateSlide = function(newIndex) {
    originalUpdateSlide(newIndex);
    requestAnimationFrame(() => {
      scaleDiagramBoards();
    });
  };

  // Khởi tạo trạng thái slide ban đầu & scale
  updateSlide(currentIndex);
  scaleDiagramBoards();
});
