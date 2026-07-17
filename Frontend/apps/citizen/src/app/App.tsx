import { BrowserRouter, Routes, Route } from 'react-router-dom';
import HomePage from '../features/home/HomePage';
import AskPage from '../features/ask/AskPage';
import VanBanPage from '../features/van-ban/VanBanPage';
import NewsPage from '../features/news/NewsPage';
import NewsDetailPage from '../features/news/NewsDetailPage';

export default function App() {
  return (
    <BrowserRouter basename="/citizen">
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/ask" element={<AskPage />} />
        <Route path="/van-ban" element={<VanBanPage />} />
        <Route path="/news" element={<NewsPage />} />
        <Route path="/news/:id" element={<NewsDetailPage />} />
      </Routes>
    </BrowserRouter>
  );
}
