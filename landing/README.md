# Cash — Landing Page

Marketing site for **Cash — The AI Operating System for Your Life**, built with
**React + TypeScript + Vite**.

## Structure

```
landing/
├── index.html              # Vite entry — loads /styles.css and mounts #root
├── public/
│   ├── styles.css          # the page's hand-authored CSS (served verbatim)
│   └── assets/
│       ├── fonts/          # self-hosted Inter + JetBrains Mono woff2 subsets
│       └── logos/          # integration / brand logos (svg + png)
└── src/
    ├── main.tsx            # React entry
    ├── App.tsx             # composes sections + boots the imperative effects
    ├── components/         # Nav, Hero, Sequence, Ethos, Compare, Marquee,
    │                       #   Footer, WaitlistModal, CashMark
    ├── lib/                # the animations + interactions, one module each
    │   ├── heroScene.ts    #   orbiting logos, phone chat loop, action toasts
    │   ├── sequence.ts     #   scroll-driven app sequence + finale
    │   ├── ethos.ts        #   scroll spotlight
    │   ├── nav.ts          #   sticky nav + mobile drawer + footer sizing
    │   ├── reveal.ts       #   IntersectionObserver reveal
    │   ├── compareTable.ts #   builds the comparison grid
    │   ├── marquee.ts      #   builds the 3 integration marquee rows
    │   ├── waitlist.ts     #   "Get access" multi-step form
    │   └── supabase.ts     #   Supabase client + waitlist insert
    └── data/               # integrations + form questions (typed)
```

### Why the CSS lives in `public/`

The visual design is a large hand-authored stylesheet whose bespoke
keyframe/SVG/canvas-style animations must render exactly as designed. Serving it
from `public/styles.css` ships it byte-for-byte (Vite copies `public/` untouched)
instead of running it through a CSS transform pipeline.

The section markup is React components; the heavy imperative choreography stays
in `src/lib` and is booted once after mount in `App.tsx`.

## Develop

```bash
npm install
cp .env.example .env     # then fill in your Supabase keys (see below)
npm run dev              # http://localhost:5173
```

## Build

```bash
npm run build            # type-checks, then outputs the static site to dist/
npm run preview          # serve the production build locally
```

## Waitlist → Supabase

The "Get access" form stores signups in a Supabase `waitlist` table. See
[`SUPABASE.md`](./SUPABASE.md) for the one-time project setup (SQL + keys). Until
configured, the form still works locally and just logs a warning instead of
writing a row.

## Deploy

`Dockerfile` builds the Vite bundle and serves `dist/` with nginx. Pass the
public Supabase values as build args:

```bash
docker build \
  --build-arg VITE_SUPABASE_URL=https://xxx.supabase.co \
  --build-arg VITE_SUPABASE_ANON_KEY=your-anon-key \
  -t cash-landing .
docker run -p 8080:80 cash-landing
```
