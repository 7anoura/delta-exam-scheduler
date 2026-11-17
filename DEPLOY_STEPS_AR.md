# Delta Exam Scheduler — Team Live Access (real university data)

## What's in this deployment folder?

- `frontend/`: current university-facing React dashboard, not the Staging QA dashboard
- `backend/`: current university-facing FastAPI code and OR-Tools solver
- `backend/data/draft_snapshot.json`: the reference snapshot the existing Dashboard uses for structural comparisons. **This may contain faculty-derived course/staff metadata.** Keep the Git repository **PRIVATE** and grant access only to authorized team members.
- `Dockerfile` and `serve.py`: serve frontend + API on ONE HTTPS URL. No frontend/backend CORS split is needed.

This pack contains no `.env`, passwords, or Supabase elevated secret keys. It does NOT automatically deploy a site or authorize anyone in Supabase.

## 1) Prepare locally

Run `prepare_online_deploy.py check` and `prepare_online_deploy.py build` from the utility folder. The output is `~/Desktop/Delta_Exam_Online_Deploy`. Check that `frontend/`, `backend/`, `Dockerfile`, and `serve.py` exist.

## 2) GitHub: PRIVATE repo

Create a **private** GitHub repo, e.g. `delta-exam-online-private`. Upload contents of the generated `Delta_Exam_Online_Deploy` directory as repository root. **Do not use the previously shared Final Project ZIP as the live source** (it was built from staging). Never upload local `.env` files or the `Project` folder. Avoid granting broad access to unreviewed collaborators.

## 3) Render: one Web Service

Visit https://dashboard.render.com and create **New > Web Service** from the private GitHub repo. Choose **Docker** runtime, root directory at repo root. Set health check path to `/health`. Choose a plan that has enough RAM for OR-Tools: Render Free has 512 MB and may spin down; test with Free if acceptable but it may run out of memory during scheduling. Upgrade/choose a suitable paid compute size if needed. Keep deploys manual while testing.

Set the environment variables in **Render > Service > Environment**:

| Name | What to enter | Exposure |
|---|---|---|
| `SUPABASE_URL` | real `delta-exam-scheduler` Project URL | server only |
| `SUPABASE_PUBLISHABLE_KEY` | publishable key for same project | server + public build |
| `SUPABASE_SECRET_KEY` | separate backend-only secret key for real project | **SERVER ONLY** |
| `VITE_SUPABASE_URL` | same real project URL | **PUBLIC** build arg |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | same real publishable key | **PUBLIC** build arg |

Do not put `SUPABASE_SECRET_KEY` into any `VITE_` variable. Do not post it to a group, GitHub issue, chat, or source code. Render Docker uses build args from environment settings. The existing Phase 9+ backend does not need an `ADMIN_DEV_TOKEN` for authentication; Supabase Auth handles access.

When deploying, verify no environment variable points to `delta-exam-scheduler-staging`. The names are similar: compare **exact project reference URL** to the original real production `.env` (without publishing the value).

## 4) Supabase Auth redirect configuration

After Render issues a URL such as `https://your-render-app.onrender.com`, use the **real** Supabase project (`delta-exam-scheduler`) > **Authentication > URL Configuration**. Set *Site URL* to that URL, and register the exact authorized redirect URL(s). Keep the existing local URL only if you still need local logins/password resets. These changes impact email confirmation and password-recovery redirects; test them carefully.

## 5) Live smoke tests — before sharing the link

1. Unauthenticated: `/health` returns 200; `/api/v1/periods` returns 401.
2. Admin logs in with the existing **real-project** Auth account: Overview contains 64 staff, 59 courses, 621 room sittings and 1,242 duties; `Version 3` is still `DRAFT`.
3. Existing staff login: only their **own published** assignments should appear. Since the real project has **no published version**, an empty staff schedule is correct. **Do not publish a real schedule just to make the portal nonempty**.
4. Confirm `/api/v1/periods` returns 403 with a staff token.
5. Verify that there are **no** `STAGING QA ONLY` controls, synthetic release shortcuts, or `sb_secret` in client assets.
6. Do not use the account temporarily linked to S001 in the real project until that test link is reviewed and removed; link real accounts only following identity verification.
7. Test Preview and scheduling on real data first under limited authorized admin access. The backend is published on the internet; review rate limits, dependency versions, logging, backups, and security posture before enabling all admins to make changes.

## 6) Real vs synthetic, roles and publication

The site uses the **same existing real Supabase project**; accounts/passwords are not migrated. Each authorized user signs in with their own account, with the existing permissions. `system_admins` grants administrative access, staff accounts have personal-schedule access only. Do not use blanket admin privileges. `Version 3` remains blocked for publication while chair coverage, Head of Control, daily limits, and source signoff are incomplete.

## 7) Updating the site later

Edit/test in a dev branch, review changes, then deploy a reviewed commit. The pack does not auto-deploy, modify the DB, or send secrets. If a secret is ever pushed to a repository, remove the exposure and **rotate** the key in Supabase.
