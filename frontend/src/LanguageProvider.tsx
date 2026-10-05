import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { LanguageContext } from './LanguageContext';
import type { Language } from './LanguageContext';

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<Language>(() =>
    localStorage.getItem('metaphor-ui-language') === 'en' ? 'en' : 'ru'
  );
  const value = useMemo(() => ({
    language,
    setLanguage: (next: Language) => {
      localStorage.setItem('metaphor-ui-language', next);
      setLanguage(next);
    },
  }), [language]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}
