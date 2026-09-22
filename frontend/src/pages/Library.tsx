import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { BookOpen, Loader2, Upload } from 'lucide-react';
import { listLibraryBooks, uploadLibraryBook } from '../api';
import type { LibraryBook } from '../api';
import { tr, useLanguage } from '../i18n';

export default function Library() {
  const { language } = useLanguage();
  const [books, setBooks] = useState<LibraryBook[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [author, setAuthor] = useState('');
  const [bookLanguage, setBookLanguage] = useState('auto');
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const refresh = async () => {
    try { setBooks((await listLibraryBooks()).items); }
    catch { setError(tr('Could not load the library.', language)); }
    finally { setLoading(false); }
  };
  useEffect(() => { refresh(); }, []);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!file) { setError(tr('Select a book file first.', language)); return; }
    setUploading(true); setError('');
    try {
      await uploadLibraryBook(file, bookLanguage, title, author);
      setFile(null); setTitle(''); setAuthor('');
      if (inputRef.current) inputRef.current.value = '';
      await refresh();
    } catch (err: any) {
      setError(err.response?.data?.detail || tr('Could not upload the book.', language));
    } finally { setUploading(false); }
  };

  return <div className="space-y-6">
    <div><h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2"><BookOpen className="w-6 h-6 text-indigo-600" />{tr('Poetry Library', language)}</h1>
      <p className="mt-1 text-gray-600">{tr('Upload books and build a searchable metaphor corpus.', language)}</p></div>
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <form onSubmit={submit} className="bg-white rounded-lg border border-gray-200 p-5 space-y-3 h-fit">
        <h2 className="font-semibold text-gray-900">{tr('Add a book', language)}</h2>
        {error && <p className="rounded bg-red-50 p-2 text-sm text-red-700">{error}</p>}
        <input ref={inputRef} type="file" accept=".txt,.pdf,.docx" onChange={e => setFile(e.target.files?.[0] ?? null)} className="block w-full text-sm" />
        <input value={title} onChange={e => setTitle(e.target.value)} placeholder={tr('Title (optional)', language)} className="w-full rounded border p-2 text-sm" />
        <input value={author} onChange={e => setAuthor(e.target.value)} placeholder={tr('Author (optional)', language)} className="w-full rounded border p-2 text-sm" />
        <select value={bookLanguage} onChange={e => setBookLanguage(e.target.value)} className="w-full rounded border p-2 text-sm"><option value="auto">{tr('Auto-detect', language)}</option><option value="zh">{tr('Chinese (zh)', language)}</option><option value="kk">{tr('Kazakh (kk)', language)}</option></select>
        <button disabled={uploading || !file} className="w-full rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{uploading ? <Loader2 className="mx-auto h-4 w-4 animate-spin" /> : <span className="flex items-center justify-center gap-2"><Upload className="h-4 w-4" />{tr('Upload and analyze', language)}</span>}</button>
      </form>
      <div className="lg:col-span-2 bg-white rounded-lg border border-gray-200 p-5">
        <h2 className="font-semibold text-gray-900 mb-4">{tr('Books in the library', language)} ({books.length})</h2>
        {loading ? <Loader2 className="h-6 w-6 animate-spin text-gray-400" /> : books.length === 0 ? <p className="text-sm text-gray-500">{tr('No books uploaded yet.', language)}</p> : <div className="space-y-3">{books.map(book => <div key={book.id} className="rounded border border-gray-200 p-4 flex items-center justify-between gap-4"><div><Link to={`/analyses/${book.analysis_id}`} className="font-medium text-indigo-700 hover:underline">{book.title}</Link><p className="text-sm text-gray-500">{book.author || tr('Unknown author', language)} · {book.language}</p><p className="text-xs text-gray-400">{book.source_name}</p></div><div className="text-right"><p className="text-sm font-medium">{tr(book.status, language)}</p><p className="text-xs text-gray-500">{book.result?.metaphors.length ?? 0} {tr('metaphors', language)}</p></div></div>)}</div>}
      </div>
    </div>
  </div>;
}
