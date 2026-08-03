import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

import { useAuth } from '../context/AuthContext';
import { API_URL } from '../services/api';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { refresh } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const formData = new URLSearchParams();
      formData.append('username', username);
      formData.append('password', password);
      const response = await axios.post(
        `${API_URL}/api/auth/login`,
        formData,
        { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
      );
      if (response.data.access_token) {
        localStorage.setItem('token', response.data.access_token);
        if (response.data.refresh_token) {
          localStorage.setItem('refresh_token', response.data.refresh_token);
        }
        await refresh();
        navigate('/dashboard');
      } else {
        setError('Respuesta inválida del servidor');
      }
    } catch (err: any) {
      if (err.response?.status === 401) {
        setError('Usuario o contraseña incorrectos');
      } else if (err.code === 'ERR_NETWORK') {
        setError('No se puede conectar al servidor');
      } else if (err.response) {
        setError(`Error ${err.response.status}: ${err.response.data?.detail || 'Error del servidor'}`);
      } else if (err.request) {
        setError('No se recibió respuesta del servidor');
      } else {
        setError(`Error: ${err.message}`);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <style>{`
        @keyframes float {
          0%, 100% { transform: translateY(0) rotate(0deg); }
          33% { transform: translateY(-18px) rotate(1deg); }
          66% { transform: translateY(10px) rotate(-1deg); }
        }
        @keyframes float-d {
          0%, 100% { transform: translateY(0) rotate(0deg); }
          33% { transform: translateY(14px) rotate(-1deg); }
          66% { transform: translateY(-8px) rotate(1deg); }
        }
        @keyframes glow-pulse {
          0%, 100% { opacity: 0.25; }
          50% { opacity: 0.55; }
        }
        @keyframes slideUp {
          from { opacity: 0; transform: translateY(28px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes shimmer {
          0% { background-position: -200% 0; }
          100% { background-position: 200% 0; }
        }
        .anim-float   { animation: float 9s ease-in-out infinite; }
        .anim-float-d { animation: float-d 11s ease-in-out 3s infinite; }
        .anim-glow    { animation: glow-pulse 5s ease-in-out infinite; }
        .anim-slide   { animation: slideUp 0.7s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
        .anim-shimmer { background-size: 200% 100%; animation: shimmer 2.5s linear infinite; }
      `}</style>

      <div className="relative min-h-screen bg-[#080808] overflow-hidden flex items-center justify-center select-none">
        {/* Diamond-pattern texture overlay */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            opacity: 0.035,
            backgroundImage: [
              'linear-gradient(45deg, #D4AF37 1px, transparent 1px)',
              'linear-gradient(-45deg, #D4AF37 1px, transparent 1px)',
            ].join(', '),
            backgroundSize: '64px 64px',
          }}
        />

        {/* Warm radial glow */}
        <div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] rounded-full pointer-events-none anim-glow"
          style={{ background: 'radial-gradient(circle, rgba(212,175,55,0.08) 0%, transparent 60%)' }}
        />

        {/* Floating geometric particles */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute top-[12%] left-[8%] w-5 h-5 border border-yeikar-primary/20 rotate-45 anim-float" />
          <div className="absolute top-[30%] right-[14%] w-7 h-7 border border-yeikar-primary/15 rotate-[18deg] anim-float-d" />
          <div className="absolute bottom-[22%] left-[18%] w-3.5 h-3.5 border border-yeikar-primary/25 -rotate-12 anim-float" />
          <div className="absolute bottom-[35%] right-[10%] w-5 h-5 border border-yeikar-primary/10 rotate-[30deg] anim-float-d" />
          <div className="absolute top-[55%] left-[4%] w-[3px] h-14 bg-gradient-to-b from-yeikar-primary/10 to-transparent rotate-[35deg] anim-float" />
          <div className="absolute top-[10%] right-[28%] w-[2px] h-20 bg-gradient-to-b from-yeikar-primary/8 to-transparent -rotate-[15deg] anim-float-d" />
          <div className="absolute top-[70%] right-[5%] w-[3px] h-10 bg-gradient-to-b from-yeikar-primary/10 to-transparent rotate-[55deg] anim-float" />
        </div>

        {/* Card */}
        <div className="relative w-full max-w-md px-5 anim-slide" style={{ animationDelay: '0ms' }}>
          <div
            className="relative bg-[#0f0f0f]/80 backdrop-blur-2xl rounded-3xl border border-yeikar-primary/10 overflow-hidden"
            style={{
              boxShadow: [
                '0 25px 60px -12px rgba(0,0,0,0.8)',
                '0 0 0 1px rgba(212,175,55,0.05) inset',
              ].join(', '),
            }}
          >
            {/* Gold accent bar */}
            <div className="h-[3px] w-full bg-gradient-to-r from-transparent via-yeikar-primary to-transparent" />

            <div className="px-8 py-10 sm:px-12 sm:py-12">
              {/* Logo */}
              <div
                className="flex justify-center mb-5 anim-slide"
                style={{ animationDelay: '100ms' }}
              >
                <div className="relative">
                  <div className="absolute inset-0 rounded-full bg-yeikar-primary/15 blur-2xl" />
                  <img
                    src="/Logo-yeikar.png"
                    alt="YEIKAR"
                    className="relative h-20 w-20 object-contain"
                  />
                </div>
              </div>

              {/* Wordmark */}
              <h1
                className="text-center font-headline text-4xl sm:text-5xl tracking-[0.22em] text-yeikar-primary anim-slide"
                style={{ animationDelay: '200ms' }}
              >
                YEIKAR
              </h1>

              {/* Gold divider */}
              <div
                className="flex justify-center my-3 anim-slide"
                style={{ animationDelay: '260ms' }}
              >
                <div className="w-14 h-px bg-gradient-to-r from-transparent via-yeikar-primary/60 to-transparent" />
              </div>

              {/* Subtitle */}
              <p
                className="text-center text-yeikar-primary/45 text-[11px] tracking-[0.25em] uppercase mb-9 anim-slide"
                style={{ animationDelay: '320ms' }}
              >
                Sistema de Gestión para Mueblería
              </p>

              {/* Error */}
              {error && (
                <div
                  className="flex items-start gap-2.5 bg-red-950/30 border border-red-800/25 text-red-400 text-sm px-4 py-3 rounded-xl mb-6 anim-slide"
                  style={{ animationDelay: '380ms' }}
                >
                  <svg className="w-4 h-4 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
                  </svg>
                  <span>{error}</span>
                </div>
              )}

              {/* Form */}
              <form onSubmit={handleSubmit} className="space-y-5">
                <div
                  className="anim-slide"
                  style={{ animationDelay: '380ms' }}
                >
                  <label className="block text-yeikar-primary/40 text-[10px] tracking-[0.2em] uppercase mb-2 font-body">
                    Usuario
                  </label>
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    disabled={loading}
                    className="w-full bg-transparent border-b-2 border-yeikar-primary/15 text-white placeholder-yeikar-primary/20 py-3 pl-0 pr-2 outline-none transition-all duration-300 text-sm tracking-wide focus:border-yeikar-primary focus:shadow-[0_2px_0_0_#D4AF37]"
                    placeholder="Ingresa tu usuario"
                    autoComplete="username"
                  />
                </div>

                <div
                  className="anim-slide"
                  style={{ animationDelay: '440ms' }}
                >
                  <label className="block text-yeikar-primary/40 text-[10px] tracking-[0.2em] uppercase mb-2 font-body">
                    Contraseña
                  </label>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    disabled={loading}
                    className="w-full bg-transparent border-b-2 border-yeikar-primary/15 text-white placeholder-yeikar-primary/20 py-3 pl-0 pr-2 outline-none transition-all duration-300 text-sm tracking-wide focus:border-yeikar-primary focus:shadow-[0_2px_0_0_#D4AF37]"
                    placeholder="Ingresa tu contraseña"
                    autoComplete="current-password"
                  />
                </div>

                <div
                  className="anim-slide pt-2"
                  style={{ animationDelay: '500ms' }}
                >
                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full relative overflow-hidden group bg-gradient-to-r from-yeikar-primary via-[#e0c04a] to-yeikar-primary text-yeikar-secondary font-headline font-bold tracking-[0.15em] py-3.5 rounded-xl transition-all duration-300 hover:shadow-[0_0_30px_-4px_rgba(212,175,55,0.5)] hover:scale-[1.01] active:scale-[0.99] disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:scale-100 text-sm"
                  >
                    <span className="relative z-10">
                      {loading ? 'INGRESANDO...' : 'INGRESAR'}
                    </span>
                    <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/15 to-transparent -skew-x-12 translate-x-[-200%] group-hover:translate-x-[200%] transition-transform duration-700 ease-in-out" />
                  </button>
                </div>
              </form>

              {/* Footer */}
              <p
                className="text-center text-yeikar-primary/12 text-[9px] tracking-[0.35em] uppercase mt-9 anim-slide"
                style={{ animationDelay: '560ms' }}
              >
                &copy; YEIKAR {new Date().getFullYear()}
              </p>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
