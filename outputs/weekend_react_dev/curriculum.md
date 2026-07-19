# Curriculum — weekend_react_dev

**Goal:** Build a small React app this weekend, something like a habit tracker with local storage
**Time budget:** 60 min · **planned watch time:** 56 min (You have 4 minutes remaining. This provides a tight, high-impact curriculum designed to fit within your weekend timeframe.)

> This highly focused, project-based curriculum is designed specifically for your weekend goal of building a React Habit Tracker. By targeting specific chapters of a masterclass habit-tracker build and pairing it with a professional custom storage hook tutorial, you will quickly cross the bridge from backend development to functional front-end engineering.

## Expertise trajectory
- **Start:** Experienced backend engineer, React beginner — Has 5 years of Python backend experience and knows general JS/npm fundamentals, but has no experience with React components, JSX, hooks, or modern SPA build systems like Vite.
- **Provisional target (pre-search estimate):** Can scaffold, build, and style a standard single-page React app with TypeScript, managing local state and persisting data via localStorage.
- **Level reached by this curriculum (grounded):** Provisional Target Met
  - By following the curated segments, you will successfully scaffold a new React app with Vite, build responsive UI components with JSX and Tailwind CSS, manage the tracker's dynamic states using standard hooks, and implement a robust custom hook to persist progress cleanly inside localStorage.

## Watch in this order

### 1. [Learn React With This One Project](https://www.youtube.com/watch?v=9aTRnV6g0eQ) — 47 min (confidence: high)
Watch only these segments:
- 1:02 → 4:24 — Setup React
- 6:27 → 19:20 — Thinking in Components / Props
- 47:55 → 70:30 — useState Hook
- 97:18 → 105:15 — useEffect Hook
**Why:** This code-along is the ultimate resource for your exact goal: building a React Habit Tracker. The 'Setup React' chapter guides you through Vite scaffolding. The component and prop segments walk you through creating standard UI building blocks, while the 'useState Hook' and 'useEffect Hook' segments show you exactly how to manage and trigger side-effects in a reactive UI.
**Covers:** Scaffolding with Vite, TypeScript, and Tailwind CSS, React Components, JSX, and Prop Types, State Management with useState and Syncing to LocalStorage, Building the Habit Tracker (Hands-on Project)
**Confidence rationale:** Web Dev Simplified explicitly uses a habit tracker project to teach these fundamental concepts, which directly aligns with your weekend goal. The chapters are highly detailed.

### 2. [Persist State to localStorage in React (Complete Tutorial)](https://www.youtube.com/watch?v=RDAFJ5ToMmQ) — 9 min (confidence: high)
Watch only these segments:
- 8:59 → 13:01 — Persisting state
- 13:01 → 18:09 — usePersistedState custom hook
**Why:** Teaches you how to cleanly encapsulate the localStorage state persistence logic into a clean custom hook (`usePersistedState`). This structure will appeal to a backend engineer's appreciation for clean architecture and reusable utility functions.
**Covers:** State Management with useState and Syncing to LocalStorage
**Confidence rationale:** The video chapters explicitly target 'Persisting state' and building a custom 'usePersistedState' hook, matching the backend-aligned styling of reusable utility hooks.

## Considered but dropped

| Video | Why it lost |
|---|---|
| [Build a Complete To-Do List App with React + Vite | Dashboard, Reminders & Local Storage Tutorial](https://www.youtube.com/watch?v=X92kk5iT8CM) | overlaps with Learn React With This One Project (9aTRnV6g0eQ) because both teach basic setup, useState, and syncing state, but 9aTRnV6g0eQ focuses on the exact requested Habit Tracker project instead of a generic To-Do List. |
| [Build a React To-Do App with Local Storage (Hooks)](https://www.youtube.com/watch?v=_xO3BkiWdJI) | overlaps with Learn React With This One Project (9aTRnV6g0eQ) because both cover creating functional stateful items and saving them to local storage, but 9aTRnV6g0eQ provides a higher-quality habit tracker scenario instead of a standard To-Do list. |
| [useEffect Hook In React / Load and Save State from LocalStorage: The 10 Days of React JS (Day 10)](https://www.youtube.com/watch?v=uRDujdtVfJs) | Dropped due to outdated styling and overlap with RDAFJ5ToMmQ for modern custom hooks state synchronization. |
| [Custom React Local Storage Hook](https://www.youtube.com/watch?v=74ThcF5JqzU) | overlaps with Persist State to localStorage in React (RDAFJ5ToMmQ) because both implement a custom hook for localStorage, but RDAFJ5ToMmQ is newer, clearer, and features more robust utils. |
| [React Persist State to LocalStorage with useEffect](https://www.youtube.com/watch?v=fTP2gi7e3k8) | Dropped because it is too brief and lacks the modular structure of creating a dedicated custom hook taught in RDAFJ5ToMmQ. |
| [React Todo App – Full Project with Hooks & LocalStorage | Beginner Friendly](https://www.youtube.com/watch?v=g_47IcYzDfA) | overlaps with Learn React With This One Project (9aTRnV6g0eQ) which covers the exact same fundamental concepts with structured chapters and a habit-focused repo. |
| [Learn How to Use Local Storage in React With an Easy-to-Understand Example](https://www.youtube.com/watch?v=N7rs5F4f6FA) | overlaps with Persist State to localStorage in React (RDAFJ5ToMmQ) because both show proper state initialization from localStorage, but RDAFJ5ToMmQ's custom hook method is cleaner. |
| [10 React Antipatterns to Avoid - Code This, Not That!](https://www.youtube.com/watch?v=b0IZo2Aho9Y) | Out of scope for a developer building their first app. Best watched after the first prototype is successfully completed. |
| [Creating a Custom React Hook for Local Storage: Persisting State Effortlessly](https://www.youtube.com/watch?v=hgts_74JjVM) | overlaps with Persist State to localStorage in React (RDAFJ5ToMmQ) because both write custom useLocalStorage hooks, but RDAFJ5ToMmQ has clear chapter navigation. |
| [React Hooks in ONE Shot 2025 [ EASIEST Explanation ] | React JS Tutorial](https://www.youtube.com/watch?v=HnXPKtro4SM) | Pure theory overview which conflicts with the learner's strong preference for project-based code-alongs. |
| [React 2021 Custom Hooks with LocalStorage & axios - Episode 18](https://www.youtube.com/watch?v=qzi-X3quu3w) | Out of scope due to its focus on third-party integrations like Axios and Star Wars API endpoints rather than local storage logic. |
| [React Search Filter with Tailwind CSS! [EASY] (Step By Step)](https://www.youtube.com/watch?v=088ty7TYxCE) | Focuses primarily on search bars and dynamic table filtering with external REST APIs rather than localStorage habit tracking. |
