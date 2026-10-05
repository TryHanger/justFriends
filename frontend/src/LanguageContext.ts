import { createContext } from 'react';

export type Language = 'ru' | 'en';

export const LanguageContext = createContext<{
  language: Language;
  setLanguage: (value: Language) => void;
}>({ language: 'ru', setLanguage: () => undefined });
