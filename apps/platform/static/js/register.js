document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("register-form");
    const statusEl = document.getElementById("register-status");
    const submitButton = form?.querySelector('button[type="submit"]');
    const usernameInput = form?.querySelector('input[name="username"]');
    const passwordInput = form?.querySelector('input[name="password"]');
    const nextInput = form?.querySelector('input[name="next"]');
    const avatarInput = document.querySelector('[data-avatar-input]');
    const avatarPreview = document.querySelector("[data-avatar-preview]");
    const avatarPlaceholder = document.querySelector("[data-avatar-placeholder]");
    const avatarFeedback = document.querySelector("[data-avatar-feedback]");

    if (!form || !statusEl || !submitButton || !usernameInput || !passwordInput) return;

    const palette = [
        ["#2563eb", "#ffffff"],
        ["#0f766e", "#ffffff"],
        ["#7c3aed", "#ffffff"],
        ["#dc2626", "#ffffff"],
        ["#ea580c", "#ffffff"],
        ["#0891b2", "#ffffff"],
    ];

    const sanitizeNext = (value) => {
        if (!value) return "";
        try {
            const url = new URL(value, window.location.origin);
            return url.origin === window.location.origin ? `${url.pathname}${url.search}${url.hash}` : "";
        } catch {
            return value.startsWith("/") ? value : "";
        }
    };

    const setStatus = (message = "", isError = false) => {
        statusEl.textContent = message;
        statusEl.classList.toggle("is-error", isError);
    };

    const setAvatarFeedback = (message = "", isError = false) => {
        if (!avatarFeedback) return;
        avatarFeedback.textContent = message;
        avatarFeedback.classList.toggle("is-error", isError);
    };

    const setFieldState = (input, isValid) => {
        input.classList.toggle("is-invalid", !isValid);
        input.setAttribute("aria-invalid", String(!isValid));
    };

    const hashCode = (value) => {
        let hash = 0;
        for (let i = 0; i < value.length; i += 1) {
            hash = (hash * 31 + value.charCodeAt(i)) >>> 0;
        }
        return hash;
    };

    const renderDefaultAvatar = () => {
        if (!avatarPlaceholder) return;
        const seed = usernameInput.value.trim() || "A";
        const initial = seed.slice(0, 1).toUpperCase();
        const index = hashCode(seed) % palette.length;
        const [bg, fg] = palette[index];
        avatarPlaceholder.textContent = initial;
        avatarPlaceholder.style.background = `linear-gradient(135deg, ${bg}, ${bg === "#2563eb" ? "#60a5fa" : "#1d4ed8"})`;
        avatarPlaceholder.style.color = fg;
        avatarPlaceholder.hidden = false;
        if (avatarPreview) avatarPreview.hidden = true;
    };

    const clearAvatarPreview = () => {
        if (avatarPreview) {
            avatarPreview.hidden = true;
            avatarPreview.removeAttribute("src");
        }
        setAvatarFeedback("Preview will appear here after you choose an image.");
        renderDefaultAvatar();
    };

    const setAvatarPreview = (file) => {
        if (!file) {
            clearAvatarPreview();
            return;
        }

        if (!file.type.startsWith("image/")) {
            if (avatarInput) avatarInput.value = "";
            clearAvatarPreview();
            setAvatarFeedback("Please choose a valid image file.", true);
            return;
        }

        const reader = new FileReader();
        reader.onload = () => {
            if (!avatarPreview || !avatarPlaceholder) return;
            avatarPreview.src = String(reader.result || "");
            avatarPreview.hidden = false;
            avatarPlaceholder.hidden = true;
            setAvatarFeedback(`Selected: ${file.name}`);
        };
        reader.onerror = () => {
            if (avatarInput) avatarInput.value = "";
            clearAvatarPreview();
            setAvatarFeedback("Preview failed to load. Please try another image.", true);
        };
        reader.readAsDataURL(file);
    };

    const validate = () => {
        const usernameOk = usernameInput.value.trim().length >= 3;
        const passwordOk = passwordInput.value.trim().length >= 6;
        setFieldState(usernameInput, usernameOk);
        setFieldState(passwordInput, passwordOk);
        return usernameOk && passwordOk;
    };

    const redirectToNext = () => {
        const next = sanitizeNext(nextInput?.value || new URLSearchParams(window.location.search).get("next") || "");
        window.location.href = next || "/";
    };

    usernameInput.addEventListener("input", () => {
        validate();
        if (!avatarInput?.files?.length) renderDefaultAvatar();
    });
    passwordInput.addEventListener("input", validate);
    usernameInput.addEventListener("blur", validate);
    passwordInput.addEventListener("blur", validate);
    avatarInput?.addEventListener("click", () => {
        avatarInput.value = "";
    });
    avatarInput?.addEventListener("change", () => {
        const file = avatarInput.files?.[0];
        setAvatarPreview(file || null);
    });

    form.addEventListener("submit", async (event) => {
        event.preventDefault();

        if (!validate()) {
            setStatus("Username must be at least 3 characters and password at least 6.", true);
            return;
        }

        const originalText = submitButton.textContent;
        const hasAvatar = Boolean(avatarInput?.files?.length);
        submitButton.disabled = true;
        submitButton.textContent = hasAvatar ? "Uploading..." : "Registering...";
        setStatus(hasAvatar ? "Uploading avatar and registering..." : "Registering...");

        try {
            const formData = new FormData(form);
            const response = await fetch("/register", {
                method: "POST",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
                credentials: "same-origin",
                body: formData,
            });

            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                setStatus(data.detail || "Registration failed.", true);
                return;
            }

            setStatus("");
            redirectToNext();
        } catch {
            setStatus("Network error. Please try again.", true);
        } finally {
            submitButton.disabled = false;
            submitButton.textContent = originalText;
        }
    });

    renderDefaultAvatar();
});
