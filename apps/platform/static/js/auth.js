window.AuthUI = window.AuthUI || {
    sanitizeNext(value) {
        if (!value) return "";
        try {
            const url = new URL(value, window.location.origin);
            return url.origin === window.location.origin ? `${url.pathname}${url.search}${url.hash}` : "";
        } catch {
            return value.startsWith("/") ? value : "";
        }
    },
    setStatus(el, message = "", isError = false) {
        if (!el) return;
        el.textContent = message;
        el.classList.toggle("is-error", isError);
    },
    setFieldState(input, isValid) {
        if (!input) return;
        input.classList.toggle("is-invalid", !isValid);
        input.setAttribute("aria-invalid", String(!isValid));
    },
    syncPasswordButton(button, isVisible) {
        if (!button) return;
        button.classList.toggle("is-visible", isVisible);
        button.setAttribute("aria-pressed", String(isVisible));
        button.setAttribute("aria-label", isVisible ? "隐藏密码" : "显示密码");
        const text = button.querySelector(".password-toggle__text");
        if (text) {
            text.textContent = isVisible ? "隐藏" : "显示";
        }
    },
};

document.addEventListener("DOMContentLoaded", () => {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
        window.lucide.createIcons();
    }

    function togglePasswordVisibility(input, button) {
        if (!input || !button) return;
        const visible = input.type === "text";
        input.type = visible ? "password" : "text";
        window.AuthUI.syncPasswordButton(button, !visible);
        input.focus();
    }

    function bindPasswordToggles(root = document) {
        root.querySelectorAll("[data-password-toggle]").forEach((button) => {
            if (button.dataset.toggleBound === "1") return;
            button.dataset.toggleBound = "1";
            const field = button.closest(".input-wrapper, .auth-password-field");
            const input = field?.querySelector("[data-password-input]");
            if (input instanceof HTMLInputElement) {
                window.AuthUI.syncPasswordButton(button, input.type === "text");
            }
            button.addEventListener("click", () => {
                const targetField = button.closest(".input-wrapper, .auth-password-field");
                const targetInput = targetField?.querySelector("[data-password-input]");
                if (targetInput instanceof HTMLInputElement) {
                    togglePasswordVisibility(targetInput, button);
                }
            });
        });
    }

    const userMenus = Array.from(document.querySelectorAll("[data-user-menu]"));
    const profileAvatarInput = document.querySelector("[data-profile-avatar-input]");
    const profileAvatarStatus = document.querySelector("[data-profile-avatar-status]");
    const currentAvatarImage = document.querySelector("[data-current-avatar-image]");
    const currentAvatarFallback = document.querySelector("[data-current-avatar-fallback]");

    const palette = [
        ["#2563eb", "#ffffff"],
        ["#0f766e", "#ffffff"],
        ["#7c3aed", "#ffffff"],
        ["#dc2626", "#ffffff"],
        ["#ea580c", "#ffffff"],
        ["#0891b2", "#ffffff"],
    ];

    function hashCode(value) {
        let hash = 0;
        for (let i = 0; i < value.length; i += 1) {
            hash = (hash * 31 + value.charCodeAt(i)) >>> 0;
        }
        return hash;
    }

    function renderFallbackAvatar(placeholder, seedValue = "") {
        if (!placeholder) return;
        const seed = (seedValue || "A").trim() || "A";
        const initial = seed.slice(0, 1).toUpperCase();
        const index = hashCode(seed) % palette.length;
        const [bg, fg] = palette[index];
        placeholder.hidden = false;
        placeholder.textContent = initial;
        placeholder.style.background = `linear-gradient(135deg, ${bg}, ${bg === "#2563eb" ? "#60a5fa" : "#1d4ed8"})`;
        placeholder.style.color = fg;
    }

    function closeUserMenus() {
        userMenus.forEach((menu) => {
            menu.classList.remove("is-open");
            const panel = menu.querySelector("[data-user-menu-panel]");
            const button = menu.querySelector("[data-user-menu-toggle]");
            if (panel) panel.hidden = true;
            if (button) button.setAttribute("aria-expanded", "false");
        });
    }

    function toggleUserMenu(menu) {
        const panel = menu.querySelector("[data-user-menu-panel]");
        const button = menu.querySelector("[data-user-menu-toggle]");
        const isOpen = menu.classList.contains("is-open");
        closeUserMenus();
        if (isOpen) return;
        menu.classList.add("is-open");
        if (panel) panel.hidden = false;
        if (button) button.setAttribute("aria-expanded", "true");
    }

    function renderAvatarMarkup(container, avatarUrl, size = "top") {
        if (!container) return;
        if (size === "top") {
            container.innerHTML = `<img class="auth-profile__avatar" src="${avatarUrl}" alt="avatar">`;
            return;
        }
        container.innerHTML = `<img class="auth-profile__menu-avatar" src="${avatarUrl}" alt="avatar">`;
    }

    function setProfileAvatar(avatarPath) {
        if (!avatarPath) return;
        const cacheBust = `?t=${Date.now()}`;
        const avatarUrl = `/static/images/${avatarPath.replace(/^\/+/, "")}${cacheBust}`;
        if (currentAvatarImage) {
            currentAvatarImage.src = avatarUrl;
            currentAvatarImage.hidden = false;
        }
        if (currentAvatarFallback) {
            currentAvatarFallback.hidden = true;
        }
        document.querySelectorAll("[data-user-menu-toggle]").forEach((button) => renderAvatarMarkup(button, avatarUrl, "top"));
        document.querySelectorAll("[data-avatar-display]").forEach((button) => renderAvatarMarkup(button, avatarUrl, "menu"));
    }

    async function uploadProfileAvatar(file) {
        if (!file) return;
        window.AuthUI.setStatus(profileAvatarStatus, "Updating avatar...");

        const formData = new FormData();
        formData.append("avatar", file);

        const response = await fetch("/profile/avatar", {
            method: "POST",
            credentials: "same-origin",
            body: formData,
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.detail || "Avatar update failed.");
        }

        setProfileAvatar(String(data.avatar_path || ""));
        window.AuthUI.setStatus(profileAvatarStatus, "Avatar updated");
        window.setTimeout(() => window.AuthUI.setStatus(profileAvatarStatus, ""), 1800);
    }

    document.querySelectorAll("[data-avatar-change-trigger]").forEach((trigger) => {
        trigger.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            if (!profileAvatarInput) return;
            profileAvatarInput.click();
        });
    });

    if (profileAvatarInput) {
        profileAvatarInput.addEventListener("change", async () => {
            const file = profileAvatarInput.files?.[0];
            if (!file) return;
            try {
                await uploadProfileAvatar(file);
            } catch (error) {
                window.AuthUI.setStatus(profileAvatarStatus, error instanceof Error ? error.message : "Avatar update failed.", true);
            } finally {
                profileAvatarInput.value = "";
            }
        });
    }

    bindPasswordToggles(document);

    document.addEventListener("click", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement)) return;

        const menuToggle = target.closest("[data-user-menu-toggle]");
        const activeMenu = target.closest("[data-user-menu]");
        if (menuToggle) {
            const menu = menuToggle.closest("[data-user-menu]");
            if (menu) toggleUserMenu(menu);
            return;
        }

        if (!activeMenu) {
            closeUserMenus();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeUserMenus();
        }
    });
});
