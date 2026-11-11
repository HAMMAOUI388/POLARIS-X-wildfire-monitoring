import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: { extend: { colors: { ink: "#142a29", forest: "#176b58", moss: "#e7f2eb", ember: "#e8754d", sand: "#f7f8f4" }, boxShadow: { card: "0 12px 34px rgba(31, 63, 54, .07)" } } },
  plugins: [],
};
export default config;
