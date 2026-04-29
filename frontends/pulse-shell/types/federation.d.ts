declare module 'feed/FeedApp' {
  interface FeedAppProps { city?: string }
  const FeedApp: React.ComponentType<FeedAppProps>
  export default FeedApp
}

declare module 'profile/ProfileApp' {
  const ProfileApp: React.ComponentType
  export default ProfileApp
}
