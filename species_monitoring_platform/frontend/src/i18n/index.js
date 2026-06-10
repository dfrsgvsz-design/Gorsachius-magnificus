import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import zh from "./zh.json";
import en from "./en.json";

const LANG_STORAGE_KEY = "species_monitoring_platform_lang";
const savedLang =
  typeof localStorage !== "undefined"
    ? localStorage.getItem(LANG_STORAGE_KEY) ||
      localStorage.getItem("bird_platform_lang") ||
      "zh"
    : "zh";

i18n.use(initReactI18next).init({
  resources: { zh: { translation: zh }, en: { translation: en } },
  lng: savedLang,
  fallbackLng: "zh",
  interpolation: { escapeValue: false },
});

export default i18n;
