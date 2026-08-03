import { Helmet } from 'react-helmet-async';

interface SEOProps {
  title: string;
  description: string;
  canonical?: string;
}

const siteName = 'Mueblería YEIKAR';

export default function SEO({ title, description, canonical }: SEOProps) {
  const fullTitle = `${title} | ${siteName}`;
  const url = canonical || 'https://yeikar.com/';

  return (
    <Helmet>
      <title>{fullTitle}</title>
      <meta name="description" content={description} />
      <link rel="canonical" href={url} />
      <meta property="og:title" content={fullTitle} />
      <meta property="og:description" content={description} />
      <meta property="og:url" content={url} />
      <meta property="og:site_name" content={siteName} />
      <meta name="twitter:title" content={fullTitle} />
      <meta name="twitter:description" content={description} />
    </Helmet>
  );
}

const organizationSchema = {
  '@context': 'https://schema.org',
  '@type': 'Organization',
  name: 'YEIKAR',
  description: 'Sistema ERP para la gestión integral de fabricación de muebles en Colombia',
  url: 'https://yeikar.com/',
  logo: 'https://yeikar.com/Logo-yeikar.png',
  contactPoint: {
    '@type': 'ContactPoint',
    contactType: 'customer service',
    availableLanguage: 'Spanish',
  },
  address: {
    '@type': 'PostalAddress',
    addressCountry: 'CO',
  },
};

export function OrganizationSchema() {
  return (
    <Helmet>
      <script type="application/ld+json">
        {JSON.stringify(organizationSchema)}
      </script>
    </Helmet>
  );
}
