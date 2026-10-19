import SignInClient from './SignInClient';
import { metadataDestino } from '@/lib/ogDestino';

/* Envoltorio de servidor del login: existe para poder armar los metadatos
   según `callbackUrl`. Un link compartido a una sección gateada (p.ej.
   /congreso) llega acá por el 307 de proxy.js, y sin esto mostraba el
   OpenGraph genérico. La UI sigue siendo la de SignInClient. */
export async function generateMetadata({ searchParams }) {
  const { callbackUrl } = await searchParams;
  return metadataDestino(callbackUrl);
}

export default function SignInPage() {
  return <SignInClient />;
}
