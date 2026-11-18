# Switch guide: demo database for the conference, then back

For the app owner, not the presenter. Placeholders only: `<LIVE_DATABASE_URL>`, `<DEMO_DATABASE_URL>`
and `<NEW_TEAM_PASSWORD>` are never written into this file. Button names in Streamlit may differ slightly.

`<DEMO_DATABASE_URL>` is the text inside `C:\Users\katei\h4d-secrets\demo_database_url.txt`.

## 1. Conference morning: switch the deployed app to the demo database

1. Go to **share.streamlit.io**, open the app, then **⋮ → Settings → Secrets**.
2. Copy the whole secrets box into a password manager or private note named "H4D live secrets".
   This is your only way back, so check that it saved.
3. On the `DATABASE_URL` line, replace the text between the quote marks with `<DEMO_DATABASE_URL>`.
   Leave `TEAM_PASSWORD` and `ANTHROPIC_API_KEY` as they are. Click **Save**.
4. Wait about a minute for the app to restart.
5. Tell your team not to use the app until you switch back. Anything saved meanwhile lands in the demo database.

## 2. Check it shows only made-up interviews

1. Open the app and log in.
2. Open **Interviews**. The dropdown must list exactly these 4, and nothing else:
   SSG Marisol Treadway, CPT Desmond Okafor, CW3 Lena Vasquez-Hart, Elliot Marsh.
3. If you see any real name, paste your saved live secrets back right away (section 4).

## 3. After the instructor's practice run: reset the demo database

Run this on your laptop from the repo folder, after the practice run and before the real demo.
It removes the practice interview and anything else added since seeding, and keeps the 4 seed
interviews, their images and the dictionary terms. It makes no AI calls and refuses to touch
the live database.

```
cd C:\Users\katei\h4d-interview-app
venv\Scripts\python scripts\seed_demo.py --url-file C:\Users\katei\h4d-secrets\demo_database_url.txt --expect-host ep-shiny-grass-beiin9bi-pooler.c-9.us-east-2.aws.neon.tech --clean-extras
```

Success ends with: `Left: 4 interviews: ['Desmond Okafor', 'Elliot Marsh', 'Lena Vasquez-Hart', 'Marisol Treadway']`

Timing rule for the presenter: the analysis usually takes about a minute. If nothing appears
after **3 minutes**, open **Interviews** and present the CPT Desmond Okafor interview instead.

## 4. After the conference: switch back to the live database

1. **⋮ → Settings → Secrets**. Replace the whole box with your saved "H4D live secrets"
   (this puts `<LIVE_DATABASE_URL>` back). Click **Save** and wait about a minute.
2. Log in and open **Interviews**. Check that all **28 real interviews** are listed, and that the
   conference's live run (1LT Jordan Vance) and the 4 demo interviews are **not**.

## 5. Change TEAM_PASSWORD (the instructor has the old one)

1. **⋮ → Settings → Secrets**. On the `TEAM_PASSWORD` line, replace the text between the quote marks
   with `<NEW_TEAM_PASSWORD>`. Click **Save**.
2. Log in with the new password to confirm it works.
3. Send the new password to your team.
4. On your laptop, put the same new password on the `TEAM_PASSWORD` line of
   `.streamlit\secrets.toml` and of `C:\Users\katei\h4d-secrets\secrets.live.toml.bak`.
