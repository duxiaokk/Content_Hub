document.addEventListener("DOMContentLoaded", () => {
    const navbar = document.getElementById("navbar");
    const revealElements = document.querySelectorAll(".reveal");
    const fallbackImages = document.querySelectorAll("img[data-fallback]");

    const handleScroll = () => {
        if (!navbar) return;
        navbar.classList.toggle("scrolled", window.scrollY > 20);
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    handleScroll();

    if (!("IntersectionObserver" in window)) {
        revealElements.forEach((el) => el.classList.add("active"));
        return;
    }

    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            if (!entry.isIntersecting) return;
            entry.target.classList.add("active");
            observer.unobserve(entry.target);
        });
    }, {
        threshold: 0.15,
        rootMargin: "0px 0px -50px 0px",
    });

    revealElements.forEach((el) => observer.observe(el));

    fallbackImages.forEach((img) => {
        img.addEventListener("error", () => {
            const fallback = img.dataset.fallback;
            if (fallback && img.src !== fallback) {
                img.src = fallback;
            }
        });
    });
});
