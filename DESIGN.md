Create the master DESIGN.md specification for a new product called “Resume Tailor”.

This DESIGN.md will be used as the source of truth for designing the product in Google Stitch.

IMPORTANT:
Do not redesign, reinterpret, simplify, or invent product functionality.
Do not add pages, features, navigation items, data, resume skills, scores, or interactions that are not specified below.

The goal is to establish a strong visual and interaction system that Stitch can use consistently across all screens.

==================================================
PRODUCT
==================================================

Resume Tailor is an AI resume-tailoring application.

Core product metaphor:

JOB
→ RESUME
→ EVIDENCE
→ TAILORING
→ FINISHED RESUME

The resume/paper is the primary visual object of the product.

The product should feel:
- alive
- responsive
- tactile
- premium
- trustworthy
- intentional

The interface should communicate what the product is doing through meaningful interaction.

Do NOT make it feel like:
- a generic AI SaaS dashboard
- a chatbot
- an analytics dashboard
- an NFT marketplace
- a glassmorphism showcase
- an animation showcase

Use motion to communicate:
- state
- transformation
- progress
- hierarchy
- feedback
- physicality

==================================================
LOCKED COLOR SYSTEM
==================================================

Background:
#eef3fb

Paper / surface:
#f7f9fc

Ink:
#0c1224

Muted text:
#5c6b82

Primary:
#0040f0

Accent:
#00a0f0

Library hover paper:
#e1e8f4

Do not introduce unrelated accent colors.

Maintain strong contrast and accessibility.

==================================================
VISUAL LANGUAGE
==================================================

Resume = paper

Ribbon = tailoring

Silk = expressive brand material

Landing = expressive product introduction

Fit a Job = interactive creation flow

Run = live tailoring process

Result = finished run analysis

Library = quiet workspace / shelf

Account = simple account/session surface

The visual metaphor should remain coherent across the product.

==================================================
MOTION SYSTEM
==================================================

Use Motion Primitives as the conceptual motion backbone.

Motion should communicate a meaningful product change.

Good uses:
- staged reveals
- page transitions
- resume transformations
- sheet expansion
- layout transitions
- progress
- feedback
- state changes
- Keep/Delete transitions

Avoid decorative motion that does not correspond to a user action or product state.

==================================================
REACT BITS
==================================================

Use React Bits selectively for signature interactions.

Potentially appropriate:
- Silk
- Blur Text
- Gradient Text
- Sliding Number
- selected micro-interactions

Do not use every available component.

The product should not feel like a component showcase.

==================================================
HAIKEI
==================================================

Use Haikei sparingly.

Primary intended use:
Landing hero → recent runs transition.

Haikei should create environmental structure rather than decorative noise.

==================================================
PAPER SHADERS
==================================================

DO NOT USE PAPER DESIGN SHADERS IN THE FIRST DESIGN BOARDS.

Paper should initially remain a flat:
#f7f9fc

The Silk effect already provides the major material treatment on Landing.

Paper shaders can be reconsidered later only if the paper genuinely needs more physicality.

==================================================
MANUS / HAPE
==================================================

Manus:
Use only as UX/product inspiration for:
- AI process presentation
- progressive disclosure
- task feedback
- complex workflow simplification

Do not copy its UI.

Hape:
Use only as visual inspiration for:
- richness
- depth
- curiosity
- premium visual confidence

Do not introduce NFT mechanics or marketplace-style UI.

==================================================
GLOBAL NAVIGATION
==================================================

Header:

Resume Tailor
Fit a job
Library
Result
Account

Wordmark → Landing.

Account contains:
- account email
- Sign out

Sign out → Landing.

==================================================
AUTH /signin
==================================================

Auth is an existing locked reference surface.

Do not redesign its structure.

Existing visual direction:
- blue Silk-style visual treatment
- light workspace/form side
- Resume Tailor branding
- clean authentication card

Displayed:
- Email
- Password
- sign-in error if applicable
- Show/Hide

Editable:
- Email
- Password

Show/Hide is visual only.

Actions:
Sign in → save session → Landing
Create account → save session → Landing
Wordmark → Landing

A signed-in user opening /signin → Landing.

Supporting copy:

“Tailor your resume to the role, using only the experience already in it.”

Do not add account settings, resume management, model selection, analytics, or other functionality here.

==================================================
LANDING /
==================================================

Purpose:
Landing is the front door.

Users should understand what Resume Tailor does, see the five-step process, upload their source resume the first time, or start fitting a job.

Hero headline:

“Your resume, fitted to the job.”

Supporting text:

“Tailor your resume to the role, using only the experience already in it.”

Primary CTA:

“Fit a job”

Hero uses:
- Silk
- Blur Text
- restrained Gradient Text where appropriate
- Motion Primitives
- Haikei transition

Silk:
body #0040f0
folds/highlights #00a0f0

Do not use white Silk highlights.

==================================================
LANDING EXAMPLE RESUME
==================================================

The resume shown in the hero is a FIXED EXAMPLE.

It is NOT the user's resume.

Never insert the user's name, real company, or uploaded resume into this example.

Five stages:

1. Reading the posting
2. Matching experience
3. Scoring the fit
4. Rewriting from facts
5. Writing the PDF

Clicking a stage changes the example.

Dragging/interacting with the paper can provide visual interaction.

The paper remains one physical object.

Stage 3 must show exactly:

86 / 97

Example match

✓ Python
✓ PostgreSQL
✓ AWS
— Kubernetes

Kubernetes is the ONLY gap.

“Example match” exists ONLY on Landing.

Do not add REST APIs, Education, or additional skills.

Stage 4 must show exactly:

Original:
“Developed backend APIs using Python.”

Tailored:
“Built backend APIs using Python for scalable services.”

Then:

“Fact preserved”

Do not invent additional facts.

Stage 5 contains:
- Experience
- AWS project
- Python
- PostgreSQL
- AWS

Do NOT add:
- REST APIs
- Education
- other invented skills

==================================================
LANDING PAPER INTERACTION
==================================================

No Tilt.

No Spotlight.

Use a restrained magnifying-lens interaction:
- small circular viewport
- follows pointer
- same resume content
- approximately 1.15x magnification
- no chromatic fringe
- no glass blob
- no glow
- no blur

Silk remains cursor-responsive independently.

==================================================
LANDING TEXT TRANSITIONS
==================================================

When changing stages:
- old content exits
- new content enters in groups
- kicker
- role
- location
- skills
- label
- sentence

Use a short stagger and blur-to-sharp transition.

Do not replace the whole paper with a different card.

==================================================
SOURCE RESUME
==================================================

The first source resume is uploaded from Landing.

Supported:
- PDF
- DOCX
- TXT

It becomes the user's fact bank.

After a source resume exists:
Landing does not show another upload control.

Replace and Remove are handled in Library.

If authentication is required before first upload:
authenticate → return to Landing → continue upload.

==================================================
RECENT RUNS ON LANDING
==================================================

Show up to three recent runs.

Display only:
- company
- role
- age

Do not show score.

Each is an individual sheet.

Hover:
- darken
- lift slightly
- soft shadow

DO NOT show the Library right-edge ribbon on Landing recent runs.

Click:
open that resume in Library:
 /library#resume-{id}

View library:
 /library

Signed out:
“Tailor your first resume for a job.”

Clicking that goes to sign-in and returns to Landing.

Signed in with no runs:
“Your first tailored resume will appear here.”

==================================================
FIT A JOB /job
==================================================

Purpose:
Choose a posting and start a tailoring run.

This page does NOT upload the source resume.

A source resume must already exist.

Display:
- “Source resume is on file.”
- search box
- Company
- Role
- job description
- rewrite model
- number of rewrites remaining today
- search results

Search results:
- company
- title
- location
- source
- snippet
- matched keywords

There are two independent job-input paths.

SEARCH:
Search or title chip → load public-board matches.

PASTE:
Company + Role + job description.

Search/paste alone never starts tailoring.

Actions:

Search / title chip:
load matches, stay on /job.

Previous / Next:
change result page.

Open posting:
open external site in new tab.

Open Google Jobs:
open Google Jobs in new tab.

The application does NOT fetch LinkedIn, Naukri, or Indeed.

Tailor resume on search hit:
start immediately → /run

Tailor this posting:
start immediately → /run
only if job description is at least 40 characters.

No second confirmation.

==================================================
RUN /run
==================================================

IMPORTANT:
The run is a persistent backend entity.

Starting a tailor creates a run ID.

The backend continues processing independently of the /run page.

Leaving /run does NOT cancel the run.

Leaving /run only removes the live view.

Returning to the same run reconnects to it.

The run lifecycle:

created
→ running
→ done

or:

running
→ failed

The /run page is a live viewer of that persistent run.

Display:
- job label
- five stages
- current stage
- live message
- climbing score /97
- step log

Five stages:

1. Reading the posting
2. Matching experience
3. Scoring the fit
4. Rewriting from facts
5. Writing the PDF

If processing is slow:
“Leave this tab open while your resume is being tailored.”

If user leaves:
run continues.

If user returns while running:
reconnect to current state.

If run finishes:
go to /result.

If run fails:
stay on /run and show error plus way back to Fit a Job.

If /run has no active/queued run:
“No run queued”
with:
“Fit a job”

The global header remains available.

==================================================
RESULT /result
==================================================

Result is a FIRST-CLASS PAGE.

It represents the finished output of one specific run.

It is NOT Library.

It is NOT the Landing example.

It does NOT contain Keep/Delete.

Display:
- company
- role
- actual run score /97
- skim
- gaps
- skills supported by the fact bank but not yet on the page
- likely rejection/concern reasons
- whether bullets were rewritten or only selected
- Download resume
- Cover letter

Do NOT show “Example match” here.

The score belongs to the actual run.

Result actions:

Download resume:
save the generated PDF.
Remain on /result.

Cover letter:
save cover_letter.txt for this same run.
Remain on /result.

Fit a job:
starts another tailoring flow.

Library:
opens Library.

If no completed result exists:
“No result yet”
with:
“Fit a job”

Do not invent per-bullet “why this was written” evidence unless that data exists.

==================================================
LIBRARY /library
==================================================

Purpose:
Manage source resume and tailored files.

Library should be quiet.

No Silk.

No Haikei.

No Paper Shader in first boards.

Paper:
#f7f9fc

==================================================
SOURCE RESUME
==================================================

One paper sheet.

Display:
- filename
- role count
- bullet count
- short fact-bank explanation
- Replace source
- Remove

Ribbon on left edge.

Example:

RitwikRNA.pdf
4 roles · 24 bullets

Your source resume used as the fact bank.

Replace source
Remove

No separate fact-bank screen.

Replace source:
upload new fact bank.

Remove:
ask confirmation.
After removal, tailoring cannot proceed until a new source is uploaded.

The next upload happens on Landing.

Do not create an “Add source” button when Library is empty.

==================================================
TAILORED RESUMES
==================================================

Each tailored resume is an individual paper sheet.

Display:
- company
- role
- age
- version

Rest:
#f7f9fc

Hover:
#e1e8f4

Hover interaction:
- translateY(-2px)
- soft shadow
- small right-edge ribbon response

Do NOT use:
- traveling highlights
- card spread
- chroma-card behavior
- collectible-card visual language

==================================================
LIBRARY DUE STATE
==================================================

If nothing is due:

“Nothing needs your attention.”

Do not explain the 7-day cycle in the empty state.

A run becomes due:
- 7 days after creation
- or 7 days after Keep

Due rows say:
“Follow-up due today.”

Clicking a due row opens the same Library sheet.

Browser notification permission may be requested once.

==================================================
OPENED LIBRARY SHEET
==================================================

Clicking a tailored resume expands it ON /library.

It does NOT navigate to /result.

Clicking the same row again closes it.

Expanded sheet actions:

Download resume
→ save PDF
→ remain on Library

Cover letter
→ save cover letter when available
→ remain on Library

Keep
→ leave file in Library
→ move follow-up 7 days out
→ sheet remains open

Delete
→ confirmation first
→ remove from Library
→ close sheet

Do not imply Resume Tailor can delete files from external services unless such an integration actually exists.

==================================================
ACCOUNT
==================================================

Account contains only:
- account email
- Sign out

Sign out → Landing.

Do not add resume management, model picker, analytics, or dashboard functionality.

==================================================
PRODUCT FLOW
==================================================

Primary flow:

Auth
→ Landing
→ Fit a Job
→ /run
→ /result

Library is accessible from the global header.

Landing recent run:
→ /library#resume-{id}

The header:
Resume Tailor
Fit a job
Library
Result
Account

==================================================
STITCH DESIGN RULE
==================================================

Preserve all functionality and information architecture above.

Do not invent:
- new pages
- dashboards
- analytics
- chat
- extra navigation
- fake resume content
- fake skills
- additional score metrics
- unsupported evidence
- unsupported integrations
- background cancellation behavior
- paper shaders in the first version

Explore visual hierarchy, composition, interaction choreography, and motion within these constraints.

The desired result is not “many animations.”

The desired result is:

“The interface responds to what I am doing, and I can see what Resume Tailor is doing.”

Landing should be the most expressive surface.

Run should feel alive because real work is happening.

Result should feel informative and finished.

Library should feel calm, physical, and trustworthy.

Use the resume/paper and ribbon metaphor consistently throughout the product.