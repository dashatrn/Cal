// 1️⃣  CSS must be imported BEFORE React so Tailwind styles land in the bundle
import "./index.css";

import React, { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.tsx";

// 2️⃣ grab the <div id="root"> in index.html
const rootElement = document.getElementById("root") as HTMLElement;

// 3️⃣ create the React root & render the App
createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>
);