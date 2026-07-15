import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

const API_URL = (import.meta as any).env?.VITE_API_URL || 'http://localhost:8000';
console.log('url', API_URL);

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

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
        { 
          headers: { 
            'Content-Type': 'application/x-www-form-urlencoded' 
          } 
        }
      );

      console.log('Respuesta del servidor:', response.data);
      
      if (response.data.access_token) {
        localStorage.setItem('token', response.data.access_token);
        navigate('/dashboard');
      } else {
        setError('Respuesta inválida del servidor');
      }
    } catch (err: any) {
  console.error('Error de login - Detalle completo:', err);
  console.error('Mensaje:', err.message);
  console.error('¿Tiene response?', err.response);
  
  if (err.response?.status === 401) {
    setError('Usuario o contraseña incorrectos');
  } else if (err.code === 'ERR_NETWORK') {
    setError('No se puede conectar al servidor. ¿El backend está corriendo en http://localhost:8000?');
  } else if (err.response) {
    setError(`Error ${err.response.status}: ${err.response.data?.detail || 'Error del servidor'}`);
  } else if (err.request) {
    setError('No se recibió respuesta del servidor. Verifica CORS o que el backend esté corriendo.');
  } else {
    setError(`Error: ${err.message}`);
  }
}
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100">
      <div className="bg-white p-8 rounded-lg shadow-md w-96">
        <h1 className="text-2xl font-bold text-center mb-6">YEIKAR ERP</h1>
        {error && (
          <div className="bg-red-100 text-red-700 p-2 rounded mb-4 text-center">
            {error}
          </div>
        )}
        <form onSubmit={handleSubmit}>
          <input
            type="text"
            placeholder="Usuario"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full p-2 border rounded mb-3"
            disabled={loading}
          />
          <input
            type="password"
            placeholder="Contraseña"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full p-2 border rounded mb-3"
            disabled={loading}
          />
          <button
            type="submit"
            className="w-full bg-blue-600 text-white p-2 rounded hover:bg-blue-700 disabled:bg-gray-400"
            disabled={loading}
          >
            {loading ? 'Iniciando...' : 'Iniciar Sesión'}
          </button>
        </form>
      </div>
    </div>
  );
}
