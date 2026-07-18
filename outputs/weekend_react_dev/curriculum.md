# Curriculum — weekend_react_dev

**Goal:** Build a small React app this weekend, something like a habit tracker with local storage
**Time budget:** 360 min · **planned watch time:** 160 min (You have 200 minutes remaining of your 360-minute budget, allowing ample time for pauses, hands-on building, and coding along.)

> This weekend curriculum is tailored for a backend engineer wanting to build a local-first React app. You'll start with a fast-paced foundational course to learn Vite, JSX, components, and basic hooks, transition to coding an interactive to-do list, and conclude by optimizing your local storage persistence with modular helper functions and a custom hook.

## Expertise trajectory
- **Start:** experienced backend engineer, React beginner — The learner has 5 years of backend engineering experience and understands core JS, npm, and general web architecture, but has no experience with React's declarative component model, stateful hooks, or modern frontend tooling like Vite.
- **Provisional target (pre-search estimate):** Capable of setting up a local development environment, structuring functional components, managing local state, and persisting state using browser localStorage to build a fully functional habit-tracker app.
- **Level reached by this curriculum (grounded):** Capable React Developer (Capable of building local-storage-backed client apps)
  - The picked curriculum covers Vite setup, JSX, component design, props, useState, useEffect, lists/keys, and state persistence. This fully supports the goal of building a custom habit tracker with clean, custom-hook-driven local storage.

## Watch in this order

### 1. [React Beginner Course 2025 (Vite, Tailwind CSS, TypeScript)](https://www.youtube.com/watch?v=siTUv1L9ymM) — 104 min (confidence: high)
**Why:** This is an exceptional developer-focused React foundation. It directly addresses the learner's unknowns by showing modern Vite setup (chapter 'React project setup...'), JSX, list rendering with map, component state ('useState + updating state in React'), and side effects with localStorage ('useEffect (side effects), local storage'). It bypasses general programming basics, making it ideal for a Python engineer.
**Covers:** Vite React Project Setup & JSX for Developers, React Components, Component Composition, & Props, State Management with useState, Managing Side Effects & Local Storage Persistence with useEffect
**Confidence rationale:** The video chapters perfectly align with the target topics, providing explicit, code-focused deep dives into Vite, components, state, and localStorage without wasting time on beginner JS syntax.

### 2. [Build a React To-Do App with Local Storage (Hooks)](https://www.youtube.com/watch?v=_xO3BkiWdJI) — 37 min (confidence: high)
**Why:** This highly structured project build aligns perfectly with the learner's weekend goal. It implements a complete CRUD task list with styling, conditional rendering, filtering, and local storage sync. Watching this fulfills the hands-on project build requirement (similar to a habit tracker).
**Covers:** Building a React Habit Tracker (Hands-on Project), State Management with useState, Managing Side Effects & Local Storage Persistence with useEffect
**Confidence rationale:** The chapters show a complete pipeline of building a functional, styled todo app with state persistence, mirroring the exact architecture needed for a habit tracker.

### 3. [Persist State to localStorage in React (Complete Tutorial)](https://www.youtube.com/watch?v=RDAFJ5ToMmQ) — 19 min (confidence: high)
**Why:** Since the learner is a backend engineer, they will appreciate writing clean, reusable, and modular code. This tutorial moves beyond basic local storage inline logic to teach creating utility functions and building a custom 'usePersistedState' hook (chapter 'usePersistedState custom hook').
**Covers:** Managing Side Effects & Local Storage Persistence with useEffect
**Confidence rationale:** Chapters specifically break down utilities vs the custom hook structure, which satisfies the learner's intermediate/advanced engineering perspective.

## Considered but dropped

| Video | Why it lost |
|---|---|
| Build a Complete To-Do List App with React + Vite | Dashboard, Reminders & Local Storage Tutorial | overlaps with Build a React To-Do App with Local Storage (Hooks) (_xO3BkiWdJI) because both show how to build a complete to-do list application using React + Vite and Local Storage, but the picked video has much clearer step-by-step chapter markers. |
| Learn React With This ONE Project | The project is a movie application that relies on fetching data from an external movie API and route structures, which does not align as closely with the local state management and localStorage requirements of a weekend habit tracker. |
| CRUD Todo App | React Typescript Project | overlaps with Build a React To-Do App with Local Storage (Hooks) (_xO3BkiWdJI) because both build a functional CRUD React app, but the picked video explicitly implements the localStorage integration which is the learner's key goal. |
| Learn useState In 15 Minutes - React Hooks Explained | It is a short hook-specific intro and overlaps with 'siTUv1L9ymM', which explains the state hooks in a more cohesive, project-driven framework. |
| All React Hooks Tutorial ( +Building Custom Hooks ) | Covers many advanced hooks like useMemo, useTransition, useReducer, and React 19 hooks that are outside the scope of building a local-storage habit tracker, introducing unnecessary complexity. |
| React Classes To Hooks: Everything about useState + useEffect | Focuses heavily on transitioning legacy class components to hooks. Since the learner has no prior exposure to React, introducing class lifecycles will only cause confusion. |
| #40: Keep Todo Data After Refresh: Adding Local Storage in React | overlaps with Persist State to localStorage in React (RDAFJ5ToMmQ) because both teach local storage data loading, but RDAFJ5ToMmQ is better tailored to a software engineer as it covers cleaner custom hooks patterns. |
| Save State to LocalStorage & Persist on Refresh with React.js | overlaps with Persist State to localStorage in React (RDAFJ5ToMmQ) which offers a cleaner utility function-oriented approach suitable for a backend developer. |
| Learn How to Use Local Storage in React With an Easy-to-Understand Example | overlaps with Persist State to localStorage in React (RDAFJ5ToMmQ) but focuses on a simple tally counter instead of robust collection data. |
| Complete React JS Tutorial for Beginners #8 - Persisting State in Local Storage | overlaps with the state persistence chapters in siTUv1L9ymM and has less structured layout. |
| Dark Mode w/ Custom React Hooks using Local Storage | The focus of this video is on building dark mode and synchronizing state across tabs, which is less relevant than building a persistent data list for a habit tracker. |
