import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import { FileText, List, BarChart2 } from 'lucide-react';
import Dashboard from './pages/Dashboard';
import AnalysisDetail from './pages/AnalysisDetail';
import Compare from './pages/Compare';

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-50 flex flex-col font-sans">
        <header className="bg-white border-b border-gray-200">
          <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
            <Link to="/" className="flex items-center gap-2 font-bold text-xl text-indigo-600">
              <FileText className="w-6 h-6" />
              Metaphor Analyzer
            </Link>
            <nav className="flex items-center gap-6">
              <Link to="/" className="text-gray-600 hover:text-indigo-600 flex items-center gap-2">
                <List className="w-4 h-4" />
                Analyses
              </Link>
              <Link to="/compare" className="text-gray-600 hover:text-indigo-600 flex items-center gap-2">
                <BarChart2 className="w-4 h-4" />
                Compare
              </Link>
            </nav>
          </div>
        </header>
        <main className="flex-1 w-full max-w-6xl mx-auto px-4 py-8">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/analyses/:id" element={<AnalysisDetail />} />
            <Route path="/compare" element={<Compare />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
