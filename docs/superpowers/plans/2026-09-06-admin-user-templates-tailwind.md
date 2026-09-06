# Admin User Templates Tailwind Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite admin/user_detail.html and admin/user_access.html with Tailwind CSS, Lucide icons, and vanilla JS, removing Bootstrap and jQuery dependencies.

**Architecture:** Both templates extend admin/base.html and use Tailwind CSS utility classes. JavaScript for modals and dynamic UI uses vanilla JS with DOMContentLoaded, no jQuery or Bootstrap JS. All modals are custom with vanilla JS show/hide logic.

**Tech Stack:** Tailwind CSS (via CDN), Lucide icons (via CDN), vanilla JavaScript, Jinja2 templates

---

## Task 1: Rewrite admin/user_detail.html

**Files:**
- Modify: `templates/admin/user_detail.html`

- [ ] **Step 1: Create complete Tailwind CSS template**

Replace entire file with Tailwind CSS version extending admin/base.html. Keep all functionality: user info card, role permissions table, site access table with manage modal, tank access table with manage modal, edit user modal, reset password modal.

Use Lucide icons instead of Font Awesome. Use vanilla JS for modal show/hide (data-modal-target attributes). Use Tailwind classes for layout, buttons, tables, badges.

Key changes:
- Replace Bootstrap grid with Tailwind flexbox/grid
- Replace Bootstrap buttons with Tailwind styled buttons
- Replace Bootstrap modals with custom vanilla JS modals
- Replace data-bs-toggle/target with data-modal-target
- Add lucide icons via <i data-lucide="..."> tags
- Inline JavaScript for modal management

- [ ] **Step 2: Verify template syntax**

Run: `python -c "import jinja2; jinja2.Template(open('templates/admin/user_detail.html').read())"` to verify Jinja2 syntax.

- [ ] **Step 3: Commit changes**

```bash
git add templates/admin/user_detail.html
git commit -m "feat: rebuild admin user detail with Tailwind CSS and vanilla JS"
```

## Task 2: Rewrite admin/user_access.html

**Files:**
- Modify: `templates/admin/user_access.html`

- [ ] **Step 1: Create complete Tailwind CSS template**

Replace entire file with Tailwind CSS version extending admin/base.html. Keep all functionality: user info display, company checkboxes, site checkboxes, form submission.

Replace jQuery with vanilla JS:
- Replace `$(document).ready()` with `DOMContentLoaded`
- Replace `$('input[name="companies"]').change()` with `document.querySelectorAll('input[name="companies"]').forEach(el => el.addEventListener('change', ...))`
- Replace jQuery `.prop('checked')` with `.checked`
- Replace jQuery `.next('label').text()` with `.nextElementSibling.textContent`
- Replace jQuery `.each()` with `.forEach()`

Use Tailwind CSS classes for layout, cards, forms, buttons. Use Lucide icons.

- [ ] **Step 2: Verify template syntax**

Run: `python -c "import jinja2; jinja2.Template(open('templates/admin/user_access.html').read())"` to verify Jinja2 syntax.

- [ ] **Step 3: Commit changes**

```bash
git add templates/admin/user_access.html
git commit -m "feat: rebuild admin user access with Tailwind CSS and vanilla JS"
```

## Task 3: Final verification and combined commit

- [ ] **Step 1: Test both templates render without errors**

Check that templates can be rendered by Jinja2 without syntax errors.

- [ ] **Step 2: Verify no jQuery or Bootstrap references**

Search for any remaining `$(`, `bootstrap`, `data-bs-` references and remove.

- [ ] **Step 3: Final commit**

```bash
git commit --amend -m "feat: rebuild admin user detail and user access with Tailwind"
```

## Execution Handoff

After saving the plan, offer execution choice:

**"Plan complete and saved to `docs/superpowers/plans/2026-09-06-admin-user-templates-tailwind.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?"**

**If Subagent-Driven chosen:**
- **REQUIRED SUB-SKILL:** Use superpowers:subagent-driven-development
- Fresh subagent per task + two-stage review

**If Inline Execution chosen:**
- **REQUIRED SUB-SKILL:** Use superpowers:executing-plans
- Batch execution with checkpoints for review
